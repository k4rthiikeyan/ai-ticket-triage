import argparse
from threading import Lock
from types import SimpleNamespace
from .config import get_settings
from .db import make_engine, migrate
from .seed import seed
from .rag import OpenRouterGateway, VectorStore
from .jobs import enqueue


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
            app = SimpleNamespace(state=SimpleNamespace(engine=engine, settings=settings, gateway=gateway,
                store=VectorStore(engine, settings.max_index_chunks), busy=False, job_lock=Lock()))
            result = enqueue(app, 'reindex')
            if result['status'] != 'succeeded':
                raise ValueError(result['error'])
            print(f"Activated {result['result']['index_id']}: {result['result']['chunks']} chunks.")
        finally:
            gateway.close()
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
