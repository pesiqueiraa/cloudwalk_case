"""broker-outbound: consome helpdesk.outbound e chama a API de callback da plataforma."""
import asyncio
import logging
from typing import Literal

import httpx
from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError

from helpdesk.broker.kafka import from_record
from helpdesk.config import Settings, get_settings
from helpdesk.contracts import AgentResult
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)

Outcome = Literal["done", "skipped", "retry"]


async def forward(result: AgentResult, client: httpx.AsyncClient, settings: Settings) -> Outcome:
    """2xx → done; 4xx → skipped (a plataforma recusou; DLQ na semana 3); resto → retry."""
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
        return "retry"
    if response.is_success:
        return "done"
    if response.is_client_error:
        log.warning("callback recusado; mensagem pulada",
                    extra={**context, "status": response.status_code, "body": response.text})
        return "skipped"
    log.warning("erro na plataforma", extra={**context, "status": response.status_code})
    return "retry"


async def run(settings: Settings) -> None:
    consumer = AIOKafkaConsumer(
        settings.topic_outbound,
        bootstrap_servers=settings.kafka_bootstrap,
        group_id="broker-outbound",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        async with httpx.AsyncClient() as client:
            async for record in consumer:
                try:
                    result = from_record(record.value, AgentResult)
                except ValidationError:
                    log.error("mensagem inválida em helpdesk.outbound; pulada", extra={"offset": record.offset})
                    await consumer.commit()
                    continue
                attempt = 0
                # Repete sem avançar o offset: preserva a ordem da partição
                while (outcome := await forward(result, client, settings)) == "retry":
                    attempt += 1
                    await asyncio.sleep(min(2 ** attempt, 30))
                await consumer.commit()
                log.info("callback entregue" if outcome == "done" else "callback pulado",
                         extra={"trace_id": result.trace_id, "event_id": result.event_id})
    finally:
        await consumer.stop()


def main() -> None:
    configure_logging("broker-outbound")
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
