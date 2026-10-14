"""Browser-test server: empty real database, explicitly mocked OpenRouter."""
from pathlib import Path
from tempfile import TemporaryDirectory
from backend.app.config import Settings
from backend.app.main import create_app
from tests.conftest import FakeGateway, FakeStore

Path('data').mkdir(exist_ok=True)
temporary = TemporaryDirectory(prefix='browser-', dir='data')
settings = Settings(database_url='sqlite:///' + (Path(temporary.name) / 'browser.db').resolve().as_posix(),
                    admin_password='test-password', _env_file=None)
app = create_app(settings, gateway=FakeGateway(), store=FakeStore())
