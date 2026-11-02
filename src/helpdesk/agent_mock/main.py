"""agent-mock: consome helpdesk.inbound, decide e publica em helpdesk.outbound."""
import asyncio
import logging

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from helpdesk.agent_mock.policy import decide
from helpdesk.broker.dlq import send_to_dlq
from helpdesk.broker.kafka import from_record, to_record
from helpdesk.config import Settings, get_settings
from helpdesk.contracts import AgentRequest
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)


async def handle_record(record, producer, settings: Settings) -> str:
    """Responde um registro, ou manda para a DLQ se o payload é inválido. O chamador commita depois."""
    try:
        req = from_record(record.value, AgentRequest)
    except ValidationError as exc:
        await send_to_dlq(producer, record, "invalid_payload", str(exc))
        return "dead_letter"
    result = decide(req)
    key, value, headers = to_record(result)
    await producer.send_and_wait(settings.topic_outbound, value=value, key=key, headers=headers)
    log.info("respondido", extra={"trace_id": req.trace_id, "event_type": result.event_type})
    return result.event_type


async def run(settings: Settings) -> None:
    consumer = AIOKafkaConsumer(
        settings.topic_inbound,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="agent-mock",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap, acks="all", enable_idempotence=True,
    )
    await consumer.start()
    await producer.start()
    try:
        async for record in consumer:
            await handle_record(record, producer, settings)
            # Offset só avança depois da resposta (ou da DLQ) publicada: at-least-once
            await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    configure_logging("agent-mock")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
