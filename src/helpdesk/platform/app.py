"""platform-web: canais de entrada, callback do broker e API de leitura."""
from contextlib import asynccontextmanager
from dataclasses import asdict
from uuid import UUID

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from helpdesk.config import get_settings
from helpdesk.contracts import AgentResult, ChatInbound, EmailInbound, WhatsAppInbound
from helpdesk.logs import configure_logging
from helpdesk.platform import admin, audit, routing
from helpdesk.platform.agent_results import ConversationNotFound, ResultMismatch, apply_agent_result
from helpdesk.platform.db import apply_schema
from helpdesk.platform.deps import get_conn
from helpdesk.platform.ingestion import DEFAULT_CLASSIFIER, ingest, normalize_chat, normalize_email, normalize_whatsapp
from helpdesk.triage.classifier import Classifier, get_classifier


def make_pool(url: str, **kwargs) -> ConnectionPool:
    # check: testa a conexão antes de entregá-la, para sobreviver a um restart do Postgres
    return ConnectionPool(
        url, kwargs={"row_factory": dict_row, "autocommit": True}, open=True,
        check=ConnectionPool.check_connection, **kwargs,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("platform-web")
    settings = get_settings()
    app.state.classifier = get_classifier(settings)
    pool = make_pool(settings.database_url)
    with pool.connection() as conn:
        apply_schema(conn)
    app.state.pool = pool
    yield
    pool.close()


app = FastAPI(title="Help Desk — plataforma", lifespan=lifespan)
app.include_router(admin.router)


def get_triage(request: Request) -> Classifier:
    # Sem o lifespan (TestClient sem "with"), usa o classificador padrão
    return getattr(request.app.state, "classifier", DEFAULT_CLASSIFIER)


Conn = Depends(get_conn)
Triage = Depends(get_triage)


@app.post("/channels/chat/messages", status_code=202)
def receive_chat(payload: ChatInbound, conn: psycopg.Connection = Conn,
                 classifier: Classifier = Triage) -> dict:
    return asdict(ingest(conn, normalize_chat(payload), classifier))


@app.post("/channels/whatsapp/messages", status_code=202)
def receive_whatsapp(payload: WhatsAppInbound, conn: psycopg.Connection = Conn,
                 classifier: Classifier = Triage) -> dict:
    return asdict(ingest(conn, normalize_whatsapp(payload), classifier))


@app.post("/channels/email/messages", status_code=202)
def receive_email(payload: EmailInbound, conn: psycopg.Connection = Conn,
                 classifier: Classifier = Triage) -> dict:
    return asdict(ingest(conn, normalize_email(payload), classifier))


@app.post("/internal/agent-results")
def receive_agent_result(result: AgentResult, conn: psycopg.Connection = Conn) -> dict:
    try:
        outcome = apply_agent_result(conn, result)
    except ConversationNotFound:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    except ResultMismatch as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Descarte também é 200: o broker não deve tentar de novo uma resposta que chegou tarde
    return {"applied": outcome == "applied", "outcome": outcome}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: UUID, conn: psycopg.Connection = Conn) -> dict:
    conversation = conn.execute("SELECT * FROM conversations WHERE id = %s", (conversation_id,)).fetchone()
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversa não encontrada")
    messages = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = %s ORDER BY created_at, id", (conversation_id,)
    ).fetchall()
    return {
        "conversation": conversation,
        "messages": messages,
        "audit": audit.list_by_conversation(conn, conversation_id),
    }


@app.get("/api/queues/{queue_id}/conversations")
def get_queue_conversations(queue_id: UUID, conn: psycopg.Connection = Conn) -> list[dict]:
    if conn.execute("SELECT 1 FROM queues WHERE id = %s", (queue_id,)).fetchone() is None:
        raise HTTPException(status_code=404, detail="fila não encontrada")
    return routing.list_queue_conversations(conn, queue_id)


@app.get("/api/traces/{trace_id}/audit")
def get_trace_audit(trace_id: UUID, conn: psycopg.Connection = Conn) -> list[dict]:
    return audit.list_by_trace(conn, trace_id)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
