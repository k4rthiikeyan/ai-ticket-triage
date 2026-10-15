"""Run the disposable-schema PostgreSQL release check with an injected Vercel URL."""
import contextlib
import io
import os
import sys
from pathlib import Path
from sqlalchemy.engine import make_url
import pytest


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root))
    raw = os.environ.get('DATABASE_URL') or os.environ.get('POSTGRES_URL')
    if not raw:
        raise SystemExit('The linked production environment did not supply a database URL.')
    url = make_url(raw)
    if not url.host or not url.host.endswith('.neon.tech'):
        raise SystemExit('Expected the linked Neon PostgreSQL database; no database work was run.')
    direct = url.set(host=url.host.replace('-pooler.', '.'))
    os.environ.update(TEST_POSTGRES_URL=direct.render_as_string(hide_password=False),
                      COOKIE_SECURE='false', ADMIN_USERNAME='admin', PUBLIC_DEMO_ENABLED='false',
                      CUSTOMER_PORTAL_ENABLED='true', AUTO_MIGRATE='true')
    # Tests create/drop only their uniquely named schema, never the public schema.
    Path('artifacts').mkdir(exist_ok=True)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
        code = pytest.main(['tests/test_postgres_integration.py', '-q',
                            '--basetemp=artifacts/pytest-hosted-postgres'])
    output = captured.getvalue()
    private_values = [raw, direct.render_as_string(hide_password=False), url.password or '']
    private_values += [value for key, value in os.environ.items()
                       if any(word in key.upper() for word in ['PASSWORD', 'API_KEY', 'TOKEN', 'SECRET', 'DATABASE_URL', 'POSTGRES_URL'])]
    for value in sorted(set(private_values), key=len, reverse=True):
        if len(value) >= 6:
            output = output.replace(value, '[redacted]')
    print(output[-10000:])
    raise SystemExit(code)


if __name__ == '__main__':
    main()
