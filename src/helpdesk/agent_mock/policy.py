"""Regras fixas do agente simulado: mesma entrada, mesma saída."""
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from helpdesk.contracts import AgentRequest, AgentResult
from helpdesk.text_match import compile_terms

ESCALATION_TERMS = {
    "pt-BR": compile_terms(["humano", "atendente", "pessoa de verdade"]),
    "en-US": compile_terms(["human", "agent", "representative"]),
}

REPLY = {
    "pt-BR": "Olá, {name}! Sou o assistente virtual da InfinitePay. Recebi sua mensagem e já estou verificando.",
    "en-US": "Hi {name}! I'm JIM's virtual assistant. I got your message and I'm looking into it.",
}

ESCALATION = {
    "pt-BR": ("Certo, {name}. Vou te transferir para um especialista.", "cliente pediu atendimento humano"),
    "en-US": ("Sure, {name}. I'm transferring you to a specialist.", "customer asked for a human"),
}


def decide(req: AgentRequest) -> AgentResult:
    escalate = ESCALATION_TERMS[req.locale].search(req.text) is not None
    if escalate:
        template, reason = ESCALATION[req.locale]
    else:
        template, reason = REPLY[req.locale], None

    return AgentResult(
        # Derivado da requisição: uma reentrega gera o mesmo event_id e a plataforma descarta a cópia
        event_id=uuid5(NAMESPACE_URL, f"agent-mock:{req.event_id}"),
        event_type="agent.escalated" if escalate else "agent.replied",
        trace_id=req.trace_id,
        conversation_id=req.conversation_id,
        in_reply_to=req.message_id,
        text=template.format(name=req.customer_name),
        reason=reason,
        occurred_at=datetime.now(timezone.utc),
    )
