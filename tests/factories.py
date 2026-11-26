"""Construtores de dados sintéticos para os testes."""
from datetime import datetime, timezone
from uuid import uuid4

from helpdesk.contracts import AgentRequest, AgentResult, ChatCustomer, ChatInbound
from helpdesk.triage.classifier import Classification


def now() -> datetime:
    return datetime.now(timezone.utc)


def chat_inbound(**overrides) -> ChatInbound:
    data = {
        "session_id": f"sess-{uuid4()}",
        "message_id": f"msg-{uuid4()}",
        "brand": "infinitepay",
        "customer": ChatCustomer(external_id="cli-001", name="Ana Teste", email="ana@example.com"),
        "text": "Minha maquininha não liga",
        "sent_at": now(),
    }
    data.update(overrides)
    return ChatInbound(**data)


def agent_request(**overrides) -> AgentRequest:
    data = {
        "event_id": uuid4(),
        "trace_id": uuid4(),
        "conversation_id": uuid4(),
        "message_id": uuid4(),
        "brand": "infinitepay",
        "locale": "pt-BR",
        "channel": "chat",
        "customer_name": "Ana Teste",
        "text": "Minha maquininha não liga",
        "occurred_at": now(),
    }
    data.update(overrides)
    return AgentRequest(**data)


def agent_result(**overrides) -> AgentResult:
    data = {
        "event_id": uuid4(),
        "event_type": "agent.replied",
        "trace_id": uuid4(),
        "conversation_id": uuid4(),
        "in_reply_to": uuid4(),
        "text": "Olá, Ana Teste!",
        "occurred_at": now(),
    }
    data.update(overrides)
    return AgentResult(**data)


def whatsapp_inbound(**overrides):
    from helpdesk.contracts import WhatsAppInbound

    data = {
        "wa_message_id": f"wamid.{uuid4().hex}",
        "from_phone": "+5500900000001",
        "profile_name": "Bruno Inventado",
        "brand": "infinitepay",
        "body": "Não recebi o pagamento",
        "timestamp": now(),
    }
    data.update(overrides)
    return WhatsAppInbound(**data)


def email_inbound(**overrides):
    from helpdesk.contracts import EmailInbound

    data = {
        "message_id": f"<{uuid4().hex}@example.com>",
        "from_address": "mary.sample@example.com",
        "from_name": "Mary Sample",
        "to_address": "support@jim.example.com",
        "brand": "jim",
        "subject": "Payout missing",
        "body_text": "I didn't get yesterday's payout.",
        "received_at": now(),
    }
    data.update(overrides)
    return EmailInbound(**data)


class RecordingClassifier:
    """Classificador falso: devolve sinais fixos e guarda o histórico que recebeu."""

    def __init__(self, frustration=2.2, wants_human=0.1, fallback_reason=None, category="hardware"):
        self.calls = []
        self.result = Classification(
            category=category, priority="normal", confidence=0.9, classifier="jev", version="jev-1.14.0/q1",
            matched_terms=(), frustration=frustration, wants_human=wants_human,
            signals={"urgent": 0.1}, fallback_reason=fallback_reason,
        )

    def classify(self, text, brand, channel, history=()):
        self.calls.append({"text": text, "history": list(history)})
        return self.result
