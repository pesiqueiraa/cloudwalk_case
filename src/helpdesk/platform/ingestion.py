"""Ingestão: converte o payload de cada canal num formato único, grava a mensagem e agenda o webhook."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg

from helpdesk.contracts import BRAND_LOCALE, AgentRequest, ChatInbound, EmailInbound, WhatsAppInbound
from helpdesk.platform import audit, outbox


@dataclass(frozen=True)
class NormalizedInbound:
    channel: str
    brand: str
    customer_external_id: str
    customer_name: str
    customer_email: str | None
    session_key: str          # identifica a conversa dentro do canal
    channel_message_id: str   # chave de idempotência da ingestão
    text: str
    sent_at: datetime


@dataclass(frozen=True)
class IngestResult:
    trace_id: UUID
    conversation_id: UUID
    message_id: UUID
    duplicate: bool


def normalize_chat(payload: ChatInbound) -> NormalizedInbound:
    return NormalizedInbound(
        channel="chat", brand=payload.brand,
        customer_external_id=payload.customer.external_id, customer_name=payload.customer.name,
        customer_email=payload.customer.email, session_key=payload.session_id,
        channel_message_id=payload.message_id, text=payload.text, sent_at=payload.sent_at,
    )


def normalize_whatsapp(payload: WhatsAppInbound) -> NormalizedInbound:
    return NormalizedInbound(
        channel="whatsapp", brand=payload.brand,
        customer_external_id=payload.from_phone, customer_name=payload.profile_name,
        customer_email=None, session_key=payload.from_phone,
        channel_message_id=payload.wa_message_id, text=payload.body, sent_at=payload.timestamp,
    )


def normalize_email(payload: EmailInbound) -> NormalizedInbound:
    # Sem threads de e-mail por enquanto: uma conversa por remetente (lista de corte do roadmap)
    return NormalizedInbound(
        channel="email", brand=payload.brand,
        customer_external_id=payload.from_address, customer_name=payload.from_name,
        customer_email=payload.from_address, session_key=payload.from_address,
        channel_message_id=payload.message_id, text=f"{payload.subject}\n\n{payload.body_text}",
        sent_at=payload.received_at,
    )


def ingest_chat(conn: psycopg.Connection, payload: ChatInbound) -> IngestResult:
    return ingest(conn, normalize_chat(payload))


def ingest(conn: psycopg.Connection, msg: NormalizedInbound) -> IngestResult:
    with conn.transaction():
        customer_id = conn.execute(
            """
            INSERT INTO customers (brand_id, external_id, name, email) VALUES (%s, %s, %s, %s)
            ON CONFLICT (brand_id, external_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (msg.brand, msg.customer_external_id, msg.customer_name, msg.customer_email),
        ).fetchone()["id"]

        conversation_id = conn.execute(
            """
            INSERT INTO conversations (brand_id, customer_id, channel, external_session_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (brand_id, channel, external_session_id) DO UPDATE SET channel = EXCLUDED.channel
            RETURNING id
            """,
            (msg.brand, customer_id, msg.channel, msg.session_key),
        ).fetchone()["id"]

        trace_id = uuid4()
        inserted = conn.execute(
            """
            INSERT INTO messages (conversation_id, trace_id, direction, author, text, channel_message_id)
            VALUES (%s, %s, 'in', 'customer', %s, %s)
            ON CONFLICT (conversation_id, channel_message_id) DO NOTHING
            RETURNING id
            """,
            (conversation_id, trace_id, msg.text, msg.channel_message_id),
        ).fetchone()

        if inserted is None:
            existing = conn.execute(
                "SELECT id, trace_id FROM messages WHERE conversation_id = %s AND channel_message_id = %s",
                (conversation_id, msg.channel_message_id),
            ).fetchone()
            return IngestResult(existing["trace_id"], conversation_id, existing["id"], duplicate=True)

        audit.record(
            conn, type="message.received", trace_id=trace_id, conversation_id=conversation_id,
            actor="platform", payload={"channel": msg.channel, "channel_message_id": msg.channel_message_id},
        )
        outbox.enqueue(conn, AgentRequest(
            event_id=uuid4(),
            trace_id=trace_id,
            conversation_id=conversation_id,
            message_id=inserted["id"],
            brand=msg.brand,
            locale=BRAND_LOCALE[msg.brand],
            channel=msg.channel,
            customer_name=msg.customer_name,
            text=msg.text,
            occurred_at=datetime.now(timezone.utc),
        ))
        return IngestResult(trace_id, conversation_id, inserted["id"], duplicate=False)
