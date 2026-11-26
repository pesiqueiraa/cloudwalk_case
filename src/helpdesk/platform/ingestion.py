"""Ingestão: converte o payload de cada canal num formato único, grava a mensagem, faz a triagem e agenda o webhook."""
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg

from helpdesk.contracts import (BRAND_LOCALE, AgentRequest, ChatInbound, EmailInbound, HistoryItem, TriageSignals,
                                WhatsAppInbound)
from helpdesk.platform import audit, handoff, outbox
from helpdesk.platform.routing import route
from helpdesk.triage import decision
from helpdesk.triage.classifier import Classification, Classifier, KeywordClassifier

DEFAULT_CLASSIFIER = KeywordClassifier()


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
    queue_id: UUID | None


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


HISTORY_MAX = 10


def _prior_context(conn: psycopg.Connection, msg: NormalizedInbound) -> tuple[bool, list[dict]]:
    """Antes da transação: a mensagem já chegou? E as últimas mensagens da conversa aberta, em ordem."""
    conversation = conn.execute(
        """
        SELECT id FROM conversations
        WHERE brand_id = %s AND channel = %s AND external_session_id = %s AND status <> 'closed'
        """,
        (msg.brand, msg.channel, msg.session_key),
    ).fetchone()
    if conversation is None:
        return False, []
    rows = conn.execute(
        """
        SELECT author, text, channel_message_id FROM messages
        WHERE conversation_id = %s ORDER BY created_at DESC, id DESC LIMIT %s
        """,
        (conversation["id"], HISTORY_MAX + 1),
    ).fetchall()
    duplicate = any(row["channel_message_id"] == msg.channel_message_id for row in rows)
    history = [{"author": row["author"], "text": row["text"]} for row in reversed(rows)][-HISTORY_MAX:]
    return duplicate, history


def ingest(conn: psycopg.Connection, msg: NormalizedInbound,
           classifier: Classifier = DEFAULT_CLASSIFIER) -> IngestResult:
    # Triagem fora da transação: a chamada ao Jev (até 1 s) não segura a trava da conversa.
    # Duplicata conhecida não é classificada de novo (a transação abaixo a devolve como duplicata)
    duplicate, history = _prior_context(conn, msg)
    classification = None if duplicate else classifier.classify(msg.text, msg.brand, msg.channel, history)
    with conn.transaction():
        # Sem UPDATE aqui: uma duplicata não pode alterar o cliente. O nome é atualizado mais abaixo
        customer = conn.execute(
            """
            INSERT INTO customers (brand_id, external_id, name, email) VALUES (%s, %s, %s, %s)
            ON CONFLICT (brand_id, external_id) DO NOTHING
            RETURNING id
            """,
            (msg.brand, msg.customer_external_id, msg.customer_name, msg.customer_email),
        ).fetchone() or conn.execute(
            "SELECT id FROM customers WHERE brand_id = %s AND external_id = %s",
            (msg.brand, msg.customer_external_id),
        ).fetchone()
        customer_id = customer["id"]

        # O DO UPDATE trava a linha da conversa até o fim da transação: duas mensagens da mesma
        # conversa não são roteadas ao mesmo tempo. O WHERE repete o predicado do índice parcial
        # conversations_one_open_per_session: conversa encerrada não conta, e a mensagem abre outra
        conversation = conn.execute(
            """
            INSERT INTO conversations (brand_id, customer_id, channel, external_session_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (brand_id, channel, external_session_id) WHERE status <> 'closed'
            DO UPDATE SET channel = EXCLUDED.channel
            RETURNING id, queue_id, priority, handled_by
            """,
            (msg.brand, customer_id, msg.channel, msg.session_key),
        ).fetchone()
        conversation_id = conversation["id"]

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
            return IngestResult(existing["trace_id"], conversation_id, existing["id"], duplicate=True,
                                queue_id=conversation["queue_id"])

        conn.execute(
            "UPDATE customers SET name = %s WHERE id = %s AND name <> %s",
            (msg.customer_name, customer_id, msg.customer_name),
        )
        audit.record(
            conn, type="message.received", trace_id=trace_id, conversation_id=conversation_id,
            actor="platform", payload={"channel": msg.channel, "channel_message_id": msg.channel_message_id},
        )
        if classification is None:
            # Raro: a cópia anterior era de uma conversa já encerrada, e esta abre outra
            classification = classifier.classify(msg.text, msg.brand, msg.channel, history)
        queue_id, handled_by = _triage(conn, classification, msg, conversation, inserted["id"], trace_id)
        if handled_by == "agent":
            queue_id, handled_by = _escalate_if_needed(conn, classification, msg, conversation_id, queue_id,
                                                       trace_id)
        if handled_by == "human":
            audit.record(
                conn, type="message.held_for_human", trace_id=trace_id, conversation_id=conversation_id,
                actor="router", payload={"queue_id": str(queue_id)},
            )
            return IngestResult(trace_id, conversation_id, inserted["id"], duplicate=False, queue_id=queue_id)

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
            history=[HistoryItem(**item) for item in history],
            triage=TriageSignals(category=classification.category, priority=classification.priority,
                                 frustration=classification.frustration),
        ))
        return IngestResult(trace_id, conversation_id, inserted["id"], duplicate=False, queue_id=queue_id)


def _triage(conn: psycopg.Connection, result: Classification, msg: NormalizedInbound, conversation: dict,
            message_id: UUID, trace_id: UUID) -> tuple[UUID, str]:
    """Grava a classificação e, se a conversa ainda não tem fila, roteia. Devolve (fila, quem atende)."""
    conversation_id = conversation["id"]
    conn.execute(
        "UPDATE messages SET category = %s, priority = %s, frustration = %s, wants_human = %s WHERE id = %s",
        (result.category, result.priority, result.frustration, result.wants_human, message_id),
    )
    payload = {"category": result.category, "priority": result.priority, "confidence": result.confidence,
               "classifier": result.classifier, "version": result.version,
               "matched_terms": list(result.matched_terms)}
    if result.frustration is not None:
        payload |= {"frustration": result.frustration, "wants_human": result.wants_human, "signals": result.signals}
    if result.fallback_reason:
        payload["fallback_reason"] = result.fallback_reason
    audit.record(
        conn, type="message.classified", trace_id=trace_id, conversation_id=conversation_id, actor="triage",
        payload=payload,
    )

    if conversation["queue_id"] is not None:
        # Conversa já roteada: não troca de fila no meio do atendimento; a prioridade só sobe
        if result.priority == "high" and conversation["priority"] != "high":
            conn.execute("UPDATE conversations SET priority = 'high' WHERE id = %s", (conversation_id,))
            audit.record(
                conn, type="conversation.priority_raised", trace_id=trace_id, conversation_id=conversation_id,
                actor="router", payload={"from": conversation["priority"], "to": "high"},
            )
        return conversation["queue_id"], conversation["handled_by"]

    chosen = route(conn, brand=msg.brand, channel=msg.channel, category=result.category, priority=result.priority)
    conn.execute(
        """
        UPDATE conversations SET queue_id = %s, priority = %s, handled_by = %s, routed_at = now()
        WHERE id = %s
        """,
        (chosen.queue_id, result.priority, chosen.first_responder, conversation_id),
    )
    audit.record(
        conn, type="conversation.routed", trace_id=trace_id, conversation_id=conversation_id, actor="router",
        payload={"queue_id": str(chosen.queue_id), "queue_name": chosen.queue_name,
                 "first_responder": chosen.first_responder, "matched_by": chosen.matched_by, "rule": chosen.rule},
    )
    return chosen.queue_id, chosen.first_responder


TRANSFER_TEXT = {
    "pt-BR": "Entendi. Vou passar você para uma pessoa da nossa equipe, que continua o atendimento por aqui.",
    "en-US": "Got it. I'm passing you to a person on our team, who will continue right here.",
}
SUMMARY_MAX = 500
FRUSTRATION_LABEL = ["calmo", "incomodado", "frustrado", "muito irritado"]   # os mesmos níveis da tela


def _escalate_if_needed(conn: psycopg.Connection, result: Classification, msg: NormalizedInbound,
                        conversation_id: UUID, queue_id: UUID, trace_id: UUID) -> tuple[UUID, str]:
    """Escalação proativa: o cliente pediu uma pessoa, ou a frustração chegou ao limiar da fila.

    Só com sinais do Jev (as regras não medem frustração nem pedido de humano), e só para conversa que
    ainda está com o agente. A mensagem não vai ao agente: a plataforma avisa o cliente e transfere.
    """
    threshold = conn.execute(
        "SELECT escalate_on_frustration FROM queues WHERE id = %s", (queue_id,)
    ).fetchone()["escalate_on_frustration"]
    if decision.asks_for_human(result.wants_human):
        reason = "cliente pediu atendimento humano (triagem)"
    elif decision.frustration_reached(result.frustration, threshold):
        score = f"{result.frustration:.1f}".replace(".", ",")
        reason = (f"cliente {FRUSTRATION_LABEL[decision.frustration_level(result.frustration)]} ({score} de 3); "
                  f"a fila passa para a equipe a partir de {FRUSTRATION_LABEL[threshold]} (triagem)")
    else:
        return queue_id, "agent"

    text = TRANSFER_TEXT[BRAND_LOCALE[msg.brand]]
    conn.execute(
        "INSERT INTO messages (conversation_id, trace_id, direction, author, text) VALUES (%s, %s, 'out', 'system', %s)",
        (conversation_id, trace_id, text),
    )
    summary = f"{msg.customer_name} ({msg.channel}): {reason}. Última mensagem: “{' '.join(msg.text.split())}”"
    if len(summary) > SUMMARY_MAX:
        summary = summary[: SUMMARY_MAX - 2] + "…”"
    to_queue = handoff.escalate(
        conn, conversation_id=conversation_id, from_queue=queue_id, trace_id=trace_id, reason=reason,
        summary=summary, actor="triage",
        extra={"frustration": result.frustration, "wants_human": result.wants_human,
               "frustration_threshold": threshold, "classifier": result.classifier, "version": result.version},
    )
    return to_queue, "human"
