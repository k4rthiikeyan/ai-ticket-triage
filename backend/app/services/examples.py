"""Explicitly labelled starter material for temporary visitor workspaces only."""
from sqlmodel import select
from fastapi import HTTPException
from ..models import Article, ArticleRevision, Ticket, TicketRevision, AppState, AuditEvent

ARTICLES = [
    ('01-billing', 'Example — Billing and refunds',
     'Example support guidance. Duplicate charges belong to Billing. Refunds, invoices, receipts, subscription charges and declined payments also belong to Billing. '
     'An approved refund can take five to ten business days to reach the original payment method. If ten business days have passed, Billing should investigate the refund reference. '
     'A delayed refund does not mean the product is unavailable.', False),
    ('02-account', 'Example — Account access',
     'Example support guidance. Password resets, sign-in problems, lost MFA authenticators, permissions and suspected account compromise belong to Account & Access. '
     'For a lost authenticator, verify the account owner and follow the approved recovery process. Never ask for a password or one-time code in a support ticket.', False),
    ('03-technical', 'Example — Technical problems',
     'Example support guidance. Crashes, failed exports, API errors, webhook timeouts, slow dashboards and service outages belong to Technical Issue. '
     'Record the error, affected feature, start time, available workaround and number of users affected. A service outage affecting all users requires urgent priority.', False),
    ('04-features', 'Example — Feature requests',
     'Example support guidance. Requests for future optional functionality such as dark mode, scheduled exports, new integrations and custom reports belong to Feature Request. '
     'Record the requested behavior and use case. A future optional feature request has low priority.', False),
    ('05-general', 'Example — General questions',
     'Example support guidance. Questions about onboarding, getting started, tutorials, documentation, supported browsers and storage limits belong to General Inquiry. '
     'Answer using documented product guidance. An ordinary informational question has normal priority.', False),
    ('99-policy', 'Example — Urgency policy',
     'Example urgency policy. Routine billing requests have normal priority. A delayed refund has normal priority if the product still works and there is no suspected fraud or compromise. '
     'A routine question or issue with a working workaround has normal priority. A work-blocking issue with no workaround has high priority. '
     'Suspected account compromise or a service outage affecting all users has urgent priority. A future optional feature request has low priority. '
     'Negated conditions, such as no account compromise, are not evidence of urgency. If the request is unrelated, ambiguous or unsupported, request human review.', True),
]

TICKETS = [
    ('refund', 'Example — Refund has not arrived',
     'My refund was approved twelve business days ago, but it has not reached my original payment account. I can still use the product. There is no account compromise or service outage. Please investigate the refund reference.'),
    ('mfa', 'Example — Lost authenticator blocks work',
     'I lost my MFA authenticator and cannot sign in. I cannot work and have no workaround. Please help me restore access through the account recovery process.'),
    ('outage', 'Example — Service down for all users',
     'The service is unavailable for all users in our team. Nobody can use the dashboard or API, and there is no workaround. Please investigate this service outage.'),
]


def load_examples(session, workspace):
    if workspace == 1:
        raise ValueError('Starter examples are only available in temporary demo workspaces.')
    # Serialize repeated clicks and preserve every user-written record.
    state = session.exec(select(AppState).where(AppState.id == workspace).with_for_update()).first()
    if state is None:
        raise HTTPException(401, 'Your demo session ended. Sign in again to continue.')
    article_count = ticket_count = 0
    if not session.exec(select(Article.id).where(Article.workspace_id == workspace)).first():
        for slug, title, body, policy in ARTICLES:
            identifier = f'starter-{workspace}-{slug}'
            session.add(Article(id=identifier, workspace_id=workspace, title=title, body=body, is_policy=policy))
            session.flush()
            session.add(ArticleRevision(article_id=identifier, revision=1, title=title, body=body, active=True))
        state.knowledge_version += 1
        session.add(state)
        article_count = len(ARTICLES)
    if not session.exec(select(Ticket.id).where(Ticket.workspace_id == workspace)).first():
        for slug, subject, body in TICKETS:
            ticket = Ticket(workspace_id=workspace, seed_key=f'starter-{workspace}-{slug}', subject=subject, body=body,
                            original_subject=subject, original_body=body)
            session.add(ticket)
            session.flush()
            session.add(TicketRevision(ticket_id=ticket.id, revision=1, subject=subject, body=body))
        ticket_count = len(TICKETS)
    if article_count or ticket_count:
        session.add(AuditEvent(workspace_id=workspace, actor='demo', action='starter_examples_loaded',
                               detail={'articles': article_count, 'tickets': ticket_count}))
    return {'articles': article_count, 'tickets': ticket_count}
