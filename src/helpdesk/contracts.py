"""Contratos trocados entre os serviços.

ChatInbound, WhatsAppInbound, EmailInbound   canais → plataforma (um payload por canal)
AgentRequest  plataforma → broker (webhook) e valor em helpdesk.inbound
AgentResult   valor em helpdesk.outbound e broker → plataforma (callback)
"""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Brand = Literal["infinitepay", "jim"]
Locale = Literal["pt-BR", "en-US"]
Channel = Literal["chat", "whatsapp", "email"]
Category = Literal["payments", "hardware", "card", "account", "fraud", "other"]
Priority = Literal["high", "normal"]

BRAND_LOCALE: dict[str, Locale] = {"infinitepay": "pt-BR", "jim": "en-US"}

TEXT_MAX = 4000
EMAIL_SUBJECT_MAX = 200
Text = Annotated[str, Field(min_length=1, max_length=TEXT_MAX)]


class ChatCustomer(BaseModel):
    external_id: str
    name: str
    email: str


class ChatInbound(BaseModel):
    session_id: str
    message_id: str
    brand: Brand
    customer: ChatCustomer
    text: Text
    sent_at: datetime


class WhatsAppInbound(BaseModel):
    wa_message_id: str
    from_phone: str
    profile_name: str
    brand: Brand
    body: Text
    timestamp: datetime


class EmailInbound(BaseModel):
    message_id: str
    from_address: str
    from_name: str
    to_address: str
    brand: Brand
    subject: Annotated[str, Field(max_length=EMAIL_SUBJECT_MAX)]
    body_text: Text
    received_at: datetime

    @model_validator(mode="after")
    def fits_agent_text(self) -> "EmailInbound":
        # A ingestão junta "assunto\n\ncorpo" num texto só, que o AgentRequest limita a TEXT_MAX
        if len(self.subject) + 2 + len(self.body_text) > TEXT_MAX:
            raise ValueError(f"assunto e corpo juntos passam de {TEXT_MAX} caracteres")
        return self


HISTORY_MAX = 10


class HistoryItem(BaseModel):
    author: Literal["customer", "agent", "analyst", "system"]
    text: Text


class TriageSignals(BaseModel):
    """O que a triagem sabe da mensagem: o agente pode ajustar o tom (frustração só com o Jev)."""
    category: Category
    priority: Priority
    frustration: Annotated[float, Field(ge=0, le=3)] | None = None


class AgentRequest(BaseModel):
    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: Literal["message.received"] = "message.received"
    trace_id: UUID
    conversation_id: UUID
    message_id: UUID
    brand: Brand
    locale: Locale
    channel: Channel
    customer_name: str
    text: Text
    occurred_at: datetime
    # Opcionais (25/11; schema_version continua 1): o agente fica sem estado e a reentrega continua segura
    history: Annotated[list[HistoryItem], Field(max_length=HISTORY_MAX)] = []   # anteriores, da mais antiga
    triage: TriageSignals | None = None


class AgentInfo(BaseModel):
    """Quem respondeu, para a auditoria: o enunciado pede o LLM "registrado com modelo, versão e configurações"."""
    impl: Literal["mock", "llm"]
    model: str | None = None
    effort: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None    # custo medido de cada resposta do LLM
    output_tokens: int | None = None


class AgentResult(BaseModel):
    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: Literal["agent.replied", "agent.escalated"]
    trace_id: UUID
    conversation_id: UUID
    in_reply_to: UUID
    text: Text
    reason: str | None = None
    # Resumo para o analista que assume o caso; obrigatório na escalação
    summary: Annotated[str, Field(max_length=500)] | None = None
    occurred_at: datetime
    agent: AgentInfo | None = None   # opcional (25/11)

    @model_validator(mode="after")
    def _escalation_has_context(self) -> "AgentResult":
        if self.event_type == "agent.escalated" and not (self.reason and self.summary):
            raise ValueError("agent.escalated precisa de reason e summary")
        return self
