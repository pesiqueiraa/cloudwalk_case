"""Fila de mensagens com erro (DLQ) no Kafka: cada tópico tem um <tópico>.dlq.

O registro vai para a DLQ igual ao original (chave, valor e headers, inclusive trace_id), com headers
que dizem o motivo e de onde veio. Uso:
    python -m helpdesk.broker.dlq list   --topic helpdesk.outbound.dlq
    python -m helpdesk.broker.dlq replay --topic helpdesk.outbound.dlq [--limit N]
O replay devolve cada registro ao tópico de origem; os consumidores são idempotentes pelo event_id.
"""
import argparse
import asyncio
import json
import logging
import sys

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from helpdesk.config import Settings, get_settings
from helpdesk.logs import configure_logging

log = logging.getLogger(__name__)

DLQ_HEADERS = ("dlq_reason", "dlq_detail", "dlq_source_topic", "dlq_source_partition", "dlq_source_offset")


def dlq_topic(topic: str) -> str:
    return f"{topic}.dlq"


def header(record, name: str) -> str | None:
    for key, value in record.headers or []:
        if key == name:
            return value.decode()
    return None


def trace_of(record) -> str | None:
    """trace_id do header ou, se faltar (produtor externo), do corpo JSON."""
    trace_id = header(record, "trace_id")
    if trace_id:
        return trace_id
    try:
        value = json.loads(record.value)
    except (TypeError, ValueError):
        return None
    return str(value["trace_id"]) if isinstance(value, dict) and value.get("trace_id") else None


def dead_letter_headers(record, reason: str, detail: str) -> list[tuple[str, bytes]]:
    original = [(k, v) for k, v in (record.headers or []) if k not in DLQ_HEADERS]
    trace_id = trace_of(record)
    if trace_id and header(record, "trace_id") is None:
        original.append(("trace_id", trace_id.encode()))
    return original + [
        ("dlq_reason", reason.encode()),
        ("dlq_detail", detail[:1000].encode()),
        ("dlq_source_topic", record.topic.encode()),
        ("dlq_source_partition", str(record.partition).encode()),
        ("dlq_source_offset", str(record.offset).encode()),
    ]


async def send_to_dlq(producer, record, reason: str, detail: str) -> None:
    """Publica na DLQ e espera a confirmação: só depois disso o consumidor pode commitar o offset."""
    await producer.send_and_wait(dlq_topic(record.topic), value=record.value, key=record.key,
                                 headers=dead_letter_headers(record, reason, detail))
    log.warning("registro enviado para a DLQ", extra={
        "trace_id": trace_of(record), "reason": reason, "detail": detail[:300],
        "topic": record.topic, "partition": record.partition, "offset": record.offset,
    })


async def replay_record(producer, record) -> str:
    source = header(record, "dlq_source_topic")
    if source is None:
        raise ValueError(f"registro sem dlq_source_topic no offset {record.offset}")
    headers = [(k, v) for k, v in (record.headers or []) if k not in DLQ_HEADERS]
    await producer.send_and_wait(source, value=record.value, key=record.key, headers=headers)
    log.info("registro devolvido ao tópico de origem",
             extra={"trace_id": header(record, "trace_id"), "topic": source, "dlq_offset": record.offset})
    return source


async def _drain(consumer, limit: int | None):
    """Lê até a DLQ ficar vazia (2 s sem registros novos) ou até o limite."""
    seen = 0
    while limit is None or seen < limit:
        batches = await consumer.getmany(timeout_ms=2000, max_records=limit - seen if limit else None)
        records = [r for batch in batches.values() for r in batch]
        if not records:
            return
        for record in records:
            yield record
            seen += 1


async def list_entries(topic: str, settings: Settings, limit: int | None) -> int:
    consumer = AIOKafkaConsumer(topic, bootstrap_servers=settings.kafka_bootstrap, group_id=None,
                                auto_offset_reset="earliest", enable_auto_commit=False)
    await consumer.start()
    count = 0
    try:
        async for record in _drain(consumer, limit):
            count += 1
            print(f"offset={record.offset} trace_id={header(record, 'trace_id')} "
                  f"motivo={header(record, 'dlq_reason')} origem={header(record, 'dlq_source_topic')} "
                  f"detalhe={header(record, 'dlq_detail')}")
    finally:
        await consumer.stop()
    return count


async def replay(topic: str, settings: Settings, limit: int | None) -> int:
    consumer = AIOKafkaConsumer(topic, bootstrap_servers=settings.kafka_bootstrap, group_id="dlq-replay",
                                auto_offset_reset="earliest", enable_auto_commit=False)
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap, acks="all", enable_idempotence=True)
    await consumer.start()
    await producer.start()
    count = 0
    try:
        async for record in _drain(consumer, limit):
            await replay_record(producer, record)
            await consumer.commit()  # depois do reenvio confirmado (at-least-once)
            count += 1
    finally:
        await consumer.stop()
        await producer.stop()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(prog="dlq")
    parser.add_argument("command", choices=["list", "replay"])
    parser.add_argument("--topic", required=True, help="tópico da DLQ, ex.: helpdesk.outbound.dlq")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    configure_logging("dlq")
    if not args.topic.endswith(".dlq"):
        print("use um tópico .dlq")
        return 2
    action = list_entries if args.command == "list" else replay
    count = asyncio.run(action(args.topic, get_settings(), args.limit))
    print(f"{count} registro(s) {'listado(s)' if args.command == 'list' else 'reenviado(s)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
