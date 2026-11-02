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

Text = Annotated[str, Field(min_length=1, max_length=4000)]


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
    subject: str
    body_text: Text
    received_at: datetime


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

    @model_validator(mode="after")
    def _escalation_has_context(self) -> "AgentResult":
        if self.event_type == "agent.escalated" and not (self.reason and self.summary):
            raise ValueError("agent.escalated precisa de reason e summary")
        return self
