"""Bootstrap configuration only; never create tickets or knowledge content."""
import hashlib
import json
from pathlib import Path
from pwdlib import PasswordHash
from sqlalchemy import delete, text
from sqlmodel import Session, select
from .models import (Admin, AppState, Queue, Category, Ticket, TicketRevision, Note,
                     Decision, Job, RecommendationRun, AuditEvent, Article, ArticleRevision)
from .config import Settings, DEMO_USERNAME, DEMO_PASSWORD

CATEGORY_SEEDS = [
    ('billing', 'Billing', 'Billing', ['invoice', 'receipt', 'refund', 'duplicate charge', 'subscription', 'payment', 'pricing', 'seat cost', 'paid plan', 'billing', 'card declined']),
    ('account-access', 'Account & Access', 'Technical Support', ['password', 'sign in', 'sign-in', 'login', 'mfa', 'authenticator', 'permission', 'invitation', 'member role', 'account compromise', 'unauthorized']),
    ('technical-issue', 'Technical Issue', 'Technical Support', ['error', 'crash', 'bug', 'api', 'webhook', 'timeout', 'slow', 'outage', 'service down', 'unavailable', 'broken', 'failed export']),
    ('feature-request', 'Feature Request', 'General Support', ['feature request', 'please add', 'could you add', 'dark mode', 'new integration', 'custom report', 'scheduled export', 'workflow trigger']),
    ('general-inquiry', 'General Inquiry', 'General Support', ['getting started', 'onboarding', 'how do i', 'documentation', 'tutorial', 'help guide', 'export csv', 'storage limit', 'supported browser', 'file-size limit']),
]


def remove_legacy_demo(session):
    """Remove tagged demo tickets and exact original articles from older installs."""
    ticket_ids = session.exec(select(Ticket.id).where(Ticket.seed_key.like('demo-%'))).all()
    if ticket_ids:
        for model in [Decision, Job, Note, AuditEvent, TicketRevision, RecommendationRun]:
            session.exec(delete(model).where(model.ticket_id.in_(ticket_ids)))
        session.exec(delete(Ticket).where(Ticket.id.in_(ticket_ids)))
    hashes = json.loads(Path(__file__).with_name('legacy_demo_hashes.json').read_text(encoding='utf-8'))
    removed = False
    for article in session.exec(select(Article).where(Article.id.in_(list(hashes)))).all():
        if hashlib.sha256(article.body.encode()).hexdigest() == hashes[article.id]:
            session.exec(delete(ArticleRevision).where(ArticleRevision.article_id == article.id))
            session.delete(article)
            removed = True
    if removed:
        state = session.get(AppState, 1)
        state.knowledge_version += 1
        state.index_id = None
        state.index_knowledge_version = 0
        state.embedding_model = None
        session.add(state)


def seed(engine, settings: Settings):
    with Session(engine) as session:
        if engine.dialect.name == 'postgresql':
            session.exec(text('SELECT pg_advisory_xact_lock(871101)'))
        if not session.exec(select(Admin)).first():
            if not settings.admin_password or settings.admin_password.startswith(('replace_', 'your_')):
                raise ValueError('Set ADMIN_PASSWORD in .env or Render environment variables before first startup.')
            session.add(Admin(username=settings.admin_username,
                              password_hash=PasswordHash.recommended().hash(settings.admin_password)))
        if settings.public_demo_enabled and not session.exec(select(Admin).where(Admin.username == DEMO_USERNAME)).first():
            session.add(Admin(username=DEMO_USERNAME,
                              password_hash=PasswordHash.recommended().hash(DEMO_PASSWORD)))
        if not session.get(AppState, 1):
            session.add(AppState())
        session.flush()
        remove_legacy_demo(session)
        queue_seeds = [(1, 'Billing'), (2, 'Technical Support'), (3, 'General Support')]
        created_queues = False
        for identifier, name in queue_seeds:
            if not session.get(Queue, identifier):
                session.add(Queue(id=identifier, name=name))
                created_queues = True
        session.flush()
        if created_queues and engine.dialect.name == 'postgresql':
            # Explicit bootstrap IDs do not advance a Postgres SERIAL sequence.
            session.exec(text("SELECT setval(pg_get_serial_sequence('queue', 'id'), "
                              "GREATEST((SELECT MAX(id) FROM queue), nextval(pg_get_serial_sequence('queue', 'id'))))"))
        queues = {name: session.get(Queue, identifier) for identifier, name in queue_seeds}
        for slug, name, destination, keywords in CATEGORY_SEEDS:
            if not session.exec(select(Category).where(Category.slug == slug)).first():
                session.add(Category(slug=slug, name=name, queue_id=queues[destination].id, keywords=keywords))
        session.commit()
