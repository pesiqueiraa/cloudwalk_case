from helpdesk.config import get_settings
from helpdesk.platform.app import make_pool


def test_pool_replaces_connections_killed_by_database_restart(db):
    pool = make_pool(get_settings().test_database_url, min_size=1, max_size=1)
    try:
        with pool.connection() as conn:
            pid = conn.execute("SELECT pg_backend_pid() AS pid").fetchone()["pid"]
        # Simula o Postgres derrubando a conexão (como num restart)
        db.execute("SELECT pg_terminate_backend(%s)", (pid,))

        with pool.connection() as conn:
            assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
    finally:
        pool.close()
