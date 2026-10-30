import pytest

from helpdesk.config import get_settings
from helpdesk.platform.db import apply_schema, connect


@pytest.fixture
def db():
    """Conexão com o banco helpdesk_test, recriado do zero a cada teste."""
    conn = connect(get_settings().test_database_url)
    conn.execute("DROP SCHEMA public CASCADE")
    conn.execute("CREATE SCHEMA public")
    apply_schema(conn)
    yield conn
    conn.close()
