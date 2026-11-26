"""Agente com LLM (Claude): mesma entrada e saída do mock, com ferramentas sintéticas.

Qualquer falha (erro da API depois das tentativas do SDK, recusa, tempo esgotado, nenhuma resposta)
vira agent.escalated com motivo "agente indisponível": o cliente nunca fica sem resposta.
"""
import logging
import re
from datetime import datetime, timezone

import anthropic

from helpdesk.agent.identity import result_event_id
from helpdesk.agent_llm.prompts import PROMPT_VERSION, SYSTEM, user_turn
from helpdesk.agent_llm.tools import ToolState, make_tools
from helpdesk.config import Settings
from helpdesk.contracts import TEXT_MAX, AgentInfo, AgentRequest, AgentResult

log = logging.getLogger(__name__)

MAX_TOKENS = 1024
MAX_ITERATIONS = 4      # rodadas de ferramenta por resposta: limita custo e tempo
SUMMARY_MAX = 500
FALLBACK_BETA = "server-side-fallback-2026-07-01"

UNAVAILABLE_TEXT = {
    "pt-BR": "Desculpe, tive um problema por aqui. Vou passar você para uma pessoa da nossa equipe.",
    "en-US": "Sorry, I ran into a problem on my side. I'm passing you to a person on our team.",
}
TRANSFER_TEXT = {
    "pt-BR": "Vou passar você para uma pessoa da nossa equipe, que continua o atendimento por aqui.",
    "en-US": "I'm passing you to a person on our team, who will continue right here.",
}


def plain(text: str) -> str:
    """Canais como WhatsApp e e-mail não renderizam markdown: tira negrito, títulos e linhas em branco."""
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{2,}", "\n", text).strip()
    return text[:TEXT_MAX]


def cap(text: str, limit: int = SUMMARY_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class LLMAgent:
    def __init__(self, client, model: str, effort: str, timeout: float):
        self.client = client
        self.model = model
        self.effort = effort
        self.timeout = timeout

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMAgent":
        if not settings.anthropic_api_key:
            raise ValueError("AGENT_IMPL=llm precisa de ANTHROPIC_API_KEY")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=2,
                                          timeout=settings.agent_llm_timeout_seconds)
        return cls(client, settings.agent_llm_model, settings.agent_llm_effort, settings.agent_llm_timeout_seconds)

    def info(self, usage: tuple[int, int] | None = None) -> AgentInfo:
        return AgentInfo(impl="llm", model=self.model, effort=self.effort, prompt_version=PROMPT_VERSION,
                         input_tokens=usage[0] if usage else None, output_tokens=usage[1] if usage else None)

    async def decide(self, req: AgentRequest) -> AgentResult:
        state = ToolState()
        tokens_in = tokens_out = 0
        last = None
        try:
            runner = self.client.beta.messages.tool_runner(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM[req.locale],
                tools=make_tools(req, state),
                messages=[{"role": "user", "content": user_turn(req)}],
                output_config={"effort": self.effort},
                max_iterations=MAX_ITERATIONS,
                betas=[FALLBACK_BETA],
                fallbacks="default",
                timeout=self.timeout,
            )
            async for message in runner:
                last = message
                tokens_in += message.usage.input_tokens
                tokens_out += message.usage.output_tokens
        except anthropic.APIError as exc:
            return self._unavailable(req, f"{type(exc).__name__}: {exc}", (tokens_in, tokens_out))

        log.info("LLM respondeu", extra={"trace_id": req.trace_id, "tools": state.calls,
                                         "input_tokens": tokens_in, "output_tokens": tokens_out})
        if last is None or last.stop_reason == "refusal":
            return self._unavailable(req, "recusa do modelo" if last else "sem resposta", (tokens_in, tokens_out))
        text = plain(" ".join(b.text for b in last.content if b.type == "text"))

        if state.escalation:
            reason, summary = state.escalation
            return self._result(req, "agent.escalated", text or TRANSFER_TEXT[req.locale],
                                (tokens_in, tokens_out), reason=cap(reason, 200), summary=cap(summary))
        if not text:
            # Ex.: acabaram as rodadas de ferramenta sem uma resposta final
            return self._unavailable(req, f"sem texto (stop_reason={last.stop_reason})", (tokens_in, tokens_out))
        return self._result(req, "agent.replied", text, (tokens_in, tokens_out))

    def _unavailable(self, req: AgentRequest, why: str, usage) -> AgentResult:
        log.warning("agente indisponível; escalando", extra={"trace_id": req.trace_id, "error": why})
        summary = cap(f"{req.customer_name} ({req.channel}). Agente indisponível ({why}). "
                      f"Última mensagem: “{req.text}”")
        return self._result(req, "agent.escalated", UNAVAILABLE_TEXT[req.locale], usage,
                            reason="agente indisponível", summary=summary)

    def _result(self, req: AgentRequest, event_type: str, text: str, usage, reason=None, summary=None) -> AgentResult:
        return AgentResult(
            event_id=result_event_id(req),
            event_type=event_type,
            trace_id=req.trace_id,
            conversation_id=req.conversation_id,
            in_reply_to=req.message_id,
            text=text,
            reason=reason,
            summary=summary,
            occurred_at=datetime.now(timezone.utc),
            agent=self.info(usage),
        )
