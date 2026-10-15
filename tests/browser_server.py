"""Browser-test server: empty real database, explicitly mocked OpenRouter."""
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.app.config import Settings
from backend.app.main import create_app
from tests.conftest import FakeGateway, FakeStore


class BrowserStore(FakeStore):
    def retrieve(self, *args, **kwargs):
        articles, policies = super().retrieve(*args, **kwargs)
        articles[0]['text'] += ' An approved refund can take five to ten business days.'
        return articles, policies

Path('data').mkdir(exist_ok=True)
temporary = TemporaryDirectory(prefix='browser-', dir='data')
settings = Settings(database_url='sqlite:///' + (Path(temporary.name) / 'browser.db').resolve().as_posix(),
                    admin_password='test-password', public_demo_enabled=True, ai_minute_limit=20, _env_file=None)
app = create_app(settings, gateway=FakeGateway(), store=BrowserStore())
