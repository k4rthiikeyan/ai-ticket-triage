import os
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def test_html_revalidates_by_content_when_deploy_file_timestamps_match(tmp_path):
    dist = tmp_path / 'frontend'
    (dist / 'assets').mkdir(parents=True)
    index = dist / 'index.html'
    settings = Settings(database_url=f'sqlite:///{(tmp_path / "cache.db").as_posix()}',
                        admin_password='test-password', _env_file=None)
    index.write_text('<html>first</html>', encoding='utf-8')
    os.utime(index, (1540000000, 1540000000))
    with TestClient(create_app(settings, frontend_dir=dist)) as client:
        first = client.get('/')
        assert first.headers['cache-control'] == 'no-store'
    # Vercel packaging can preserve identical size and timestamps across builds.
    index.write_text('<html>other</html>', encoding='utf-8')
    os.utime(index, (1540000000, 1540000000))
    with TestClient(create_app(settings, frontend_dir=dist)) as client:
        second = client.get('/', headers={'If-None-Match': first.headers['etag']})
        assert second.status_code == 200 and second.text == '<html>other</html>'
        assert second.headers['etag'] != first.headers['etag']
        assert second.headers['cache-control'] == 'no-store'
        assert second.headers['vercel-cdn-cache-control'] == 'no-store'
