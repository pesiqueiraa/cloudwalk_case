"""Contratos trocados entre os serviços.

ChatInbound, WhatsAppInbound, EmailInbound   canais → plataforma (um payload por canal)
AgentRequest  plataforma → broker (webhook) e valor em helpdesk.inbound
AgentResult   valor em helpdesk.outbound e broker → plataforma (callback)
"""
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

Brand = Literal["infinitepay", "jim"]
Locale = Literal["pt-BR", "en-US"]
Channel = Literal["chat", "whatsapp", "email"]

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
    occurred_at: datetime
