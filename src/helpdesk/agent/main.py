"""agent: consome helpdesk.inbound, decide e publica em helpdesk.outbound.

A decisão é trocável (AGENT_IMPL): "mock" é determinístico e mede a plataforma no experimento;
"llm" usa o Claude com ferramentas sintéticas. O laço de consumo, a DLQ e o commit são os mesmos.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from helpdesk.agent_mock.policy import decide as mock_decide
from helpdesk.broker.dlq import send_to_dlq
from helpdesk.broker.kafka import from_record, to_record
from helpdesk.config import Settings, get_settings
from helpdesk.contracts import AgentRequest, AgentResult
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)

Decide = Callable[[AgentRequest], Awaitable[AgentResult]]


async def decide_with_mock(req: AgentRequest) -> AgentResult:
    return mock_decide(req)


async def handle_record(record, producer, settings: Settings, decide: Decide = decide_with_mock) -> str:
    """Responde um registro, ou manda para a DLQ se o payload é inválido. O chamador commita depois."""
    try:
        req = from_record(record.value, AgentRequest)
    except ValidationError as exc:
        await send_to_dlq(producer, record, "invalid_payload", str(exc))
        return "dead_letter"
    result = await decide(req)
    key, value, headers = to_record(result)
    await producer.send_and_wait(settings.topic_outbound, value=value, key=key, headers=headers)
    log.info("respondido", extra={"trace_id": req.trace_id, "event_type": result.event_type})
    return result.event_type


def make_decide(settings: Settings) -> Decide:
    if settings.agent_impl == "mock":
        return decide_with_mock
    if settings.agent_impl == "llm":
        from helpdesk.agent_llm.policy import LLMAgent

        return LLMAgent.from_settings(settings).decide
    raise ValueError(f"agente desconhecido: {settings.agent_impl}")


async def run(settings: Settings) -> None:
    decide = make_decide(settings)
    consumer = AIOKafkaConsumer(
        settings.topic_inbound,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="agent",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap, acks="all", enable_idempotence=True,
    )
    await consumer.start()
    await producer.start()
    log.info("agente no ar", extra={"agent_impl": settings.agent_impl})
    try:
        async for record in consumer:
            await handle_record(record, producer, settings, decide)
            # Offset só avança depois da resposta (ou da DLQ) publicada: at-least-once
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    configure_logging("agent")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
