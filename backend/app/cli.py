import argparse
from sqlmodel import Session, select
from .config import get_settings
from .db import make_engine, migrate
from .models import AppState, Article
from .seed import seed
from .rag import OpenRouterGateway, VectorStore


def main():
    parser = argparse.ArgumentParser(description='Triage Desk database and knowledge setup')
    parser.add_argument('command', choices=['init', 'reindex'])
    args = parser.parse_args()
    settings = get_settings()
    engine = make_engine(settings)
    migrate(engine)
    seed(engine, settings)
    try:
        if args.command == 'init':
            print('Database ready. Administrator and routing configured; no demo content added.')
            return
        gateway = OpenRouterGateway(settings)
        try:
            with Session(engine) as session:
                state = session.get(AppState, 1)
                articles = session.exec(select(Article).where(Article.active == True)).all()
                if not any(a.is_policy for a in articles):
                    raise ValueError('Add an urgency policy in Knowledge base before indexing.')
                index, count = VectorStore(engine, settings.max_index_chunks).build(articles, gateway, print)
                state.index_id, state.index_knowledge_version = index, state.knowledge_version
                state.embedding_model = settings.embedding_model
                session.add(state)
                session.commit()
                print(f'Activated {index}: {count} chunks.')
        finally:
            gateway.close()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
