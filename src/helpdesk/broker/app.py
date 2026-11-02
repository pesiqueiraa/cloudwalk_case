"""broker: recebe o webhook da plataforma e publica em helpdesk.inbound."""
import logging
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from fastapi import FastAPI, HTTPException, Request

from helpdesk.broker.kafka import to_record
from helpdesk.config import get_settings
from helpdesk.contracts import AgentRequest
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("broker")
    producer = AIOKafkaProducer(
        bootstrap_servers=get_settings().kafka_bootstrap, acks="all", enable_idempotence=True,
    )
    await producer.start()
    app.state.producer = producer
    yield
    await producer.stop()


app = FastAPI(title="Help Desk — broker", lifespan=lifespan)


@app.post("/webhooks/agent-requests", status_code=202)
async def receive_agent_request(body: AgentRequest, request: Request) -> dict:
    key, value, headers = to_record(body)
    context = {"trace_id": body.trace_id, "conversation_id": body.conversation_id, "event_id": body.event_id}
    header_trace = request.headers.get("X-Trace-Id")
    if header_trace and header_trace != str(body.trace_id):
        log.warning("X-Trace-Id diferente do trace_id do corpo", extra={**context, "header_trace_id": header_trace})
    try:
        await request.app.state.producer.send_and_wait(
            get_settings().topic_inbound, value=value, key=key, headers=headers,
        )
    except KafkaError as exc:
        log.error("falha ao publicar no Kafka", extra={**context, "error": str(exc)})
        raise HTTPException(status_code=503, detail="Kafka indisponível") from exc
    log.info("publicado em helpdesk.inbound", extra=context)
    return {"status": "accepted"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
