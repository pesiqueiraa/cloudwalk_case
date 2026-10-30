from importlib.resources import files

import psycopg
from psycopg.rows import dict_row


def connect(url: str) -> psycopg.Connection:
    """Conexão em autocommit: cada operação com mais de um efeito abre conn.transaction()."""
    return psycopg.connect(url, row_factory=dict_row, autocommit=True)


def apply_schema(conn: psycopg.Connection) -> None:
    sql = files("helpdesk.platform").joinpath("schema.sql").read_text()
    with conn.transaction():
        conn.execute(sql)
