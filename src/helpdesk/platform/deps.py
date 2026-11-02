"""Dependências do FastAPI compartilhadas pelos routers do platform-web."""
from fastapi import Request


def get_conn(request: Request):
    with request.app.state.pool.connection() as conn:
        yield conn
