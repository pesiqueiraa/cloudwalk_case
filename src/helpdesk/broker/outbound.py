"""broker-outbound: consome helpdesk.outbound e chama a API de callback da plataforma."""
import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

import httpx
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from pydantic import ValidationError

from helpdesk.broker.dlq import send_to_dlq
from helpdesk.broker.kafka import from_record
from helpdesk.config import Settings, get_settings
from helpdesk.contracts import AgentResult
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)

Outcome = Literal["done", "retry", "dead_letter"]

# 4xx que são passageiros: timeout do servidor e limite de taxa
RETRYABLE_STATUS = {408, 429}


@dataclass(frozen=True)
class Delivery:
    outcome: Outcome
    detail: str = ""


async def forward(result: AgentResult, client: httpx.AsyncClient, settings: Settings) -> Delivery:
    """2xx → done; 408, 429, 5xx e falha de rede → retry; outros 4xx → dead_letter (a plataforma recusou)."""
    context = {"trace_id": result.trace_id, "event_id": result.event_id}
    try:
        response = await client.post(
            f"{settings.platform_url}/internal/agent-results",
            content=result.model_dump_json(),
            headers={"Content-Type": "application/json", "X-Trace-Id": str(result.trace_id)},
            timeout=5,
        )
    except httpx.HTTPError as exc:
        log.warning("plataforma inacessível", extra={**context, "error": str(exc)})
        return Delivery("retry", str(exc))
    if response.is_success:
        return Delivery("done")
    detail = f"{response.status_code}: {response.text[:500]}"
    if response.status_code in RETRYABLE_STATUS or response.is_server_error:
        log.warning("plataforma pediu nova tentativa", extra={**context, "status": response.status_code})
        return Delivery("retry", detail)
    return Delivery("dead_letter", detail)


async def handle_record(record, client: httpx.AsyncClient, producer, settings: Settings,
                        sleep=asyncio.sleep) -> Outcome:
    """Entrega um registro. Só volta quando ele foi entregue ou foi para a DLQ: o chamador commita depois."""
    try:
        result = from_record(record.value, AgentResult)
    except ValidationError as exc:
        await send_to_dlq(producer, record, "invalid_payload", str(exc))
        return "dead_letter"

    context = {"trace_id": result.trace_id, "event_id": result.event_id}
    attempt = 0
    # Repete sem avançar o offset: preserva a ordem da partição
    while (delivery := await forward(result, client, settings)).outcome == "retry":
        attempt += 1
        await sleep(min(2 ** attempt, 30))
    if delivery.outcome == "dead_letter":
        await send_to_dlq(producer, record, "callback_rejected", delivery.detail)
    else:
        log.info("callback entregue", extra={**context, "retries": attempt})
    return delivery.outcome


async def run(settings: Settings) -> None:
    consumer = AIOKafkaConsumer(
        settings.topic_outbound,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="broker-outbound",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap, acks="all", enable_idempotence=True)
    await consumer.start()
    await producer.start()
    try:
        async with httpx.AsyncClient() as client:
            async for record in consumer:
                await handle_record(record, client, producer, settings)
                await consumer.commit()
    finally:
        await consumer.stop()
        await producer.stop()


def main() -> None:
    configure_logging("broker-outbound")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
