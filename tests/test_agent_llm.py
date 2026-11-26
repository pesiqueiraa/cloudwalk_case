"""Agente com LLM, com um cliente falso: nenhum teste chama a API da Anthropic."""
from types import SimpleNamespace

import anthropic
import httpx

from helpdesk.agent.identity import result_event_id
from helpdesk.agent_llm.policy import LLMAgent, plain
from helpdesk.agent_llm.prompts import PROMPT_VERSION, user_turn
from helpdesk.agent_mock.policy import decide as mock_decide
from tests.factories import agent_request


def message(text="", stop_reason="end_turn", tokens=(100, 20)):
    content = [SimpleNamespace(type="text", text=text)] if text else []
    return SimpleNamespace(content=content, stop_reason=stop_reason,
                           usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]))


class FakeRunner:
    def __init__(self, script, tools):
        self.script, self.tools = script, {t.name: t for t in tools}

    def __aiter__(self):
        return self._run()

    async def _run(self):
        for step in self.script:
            if isinstance(step, Exception):
                raise step
            if isinstance(step, tuple):   # ("ferramenta", {entrada}): o runner executa a ferramenta
                name, args = step
                await self.tools[name].call(args)
                yield message(stop_reason="tool_use")
            else:
                yield step


class FakeClient:
    def __init__(self, *script):
        self.script, self.calls = script, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(tool_runner=self._tool_runner))

    def _tool_runner(self, **kwargs):
        self.calls.append(kwargs)
        return FakeRunner(self.script, kwargs["tools"])


def agent(*script):
    client = FakeClient(*script)
    return LLMAgent(client, "claude-sonnet-5-5", "low", 30.0), client


async def test_reply_carries_model_prompt_version_and_tokens():
    llm, client = agent(("consultar_transacoes", {"dias": 2}), message("Sua venda cai amanhã."))
    req = agent_request()
    result = await llm.decide(req)

    assert (result.event_type, result.text) == ("agent.replied", "Sua venda cai amanhã.")
    assert result.agent.model_dump() == {"impl": "llm", "model": "claude-sonnet-5-5", "effort": "low",
                                         "prompt_version": PROMPT_VERSION, "input_tokens": 200, "output_tokens": 40}
    call = client.calls[0]
    assert (call["output_config"], call["fallbacks"], call["max_iterations"]) == ({"effort": "low"}, "default", 4)


async def test_same_request_gives_same_event_id_as_the_mock():
    # Reentrega (ou troca de implementação no meio dela): a plataforma descarta a cópia pelo event_id
    req = agent_request()
    llm, _ = agent(message("Oi!"))
    assert (await llm.decide(req)).event_id == mock_decide(req).event_id == result_event_id(req)


async def test_escalation_tool_becomes_agent_escalated():
    llm, _ = agent(("escalar_para_humano", {"motivo": "suspeita de fraude", "resumo": "Compra de R$ 900 não reconhecida."}),
                   message("Vou transferir você para um especialista."))
    result = await llm.decide(agent_request())
    assert (result.event_type, result.reason) == ("agent.escalated", "suspeita de fraude")
    assert result.summary == "Compra de R$ 900 não reconhecida."
    assert result.text == "Vou transferir você para um especialista."


async def test_escalation_without_text_gets_a_transfer_message():
    llm, _ = agent(("escalar_para_humano", {"motivo": "pediu humano", "resumo": "Quer uma pessoa."}), message())
    result = await llm.decide(agent_request())
    assert result.event_type == "agent.escalated"
    assert result.text.startswith("Vou passar você")


async def test_api_error_escalates_as_unavailable():
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    llm, _ = agent(anthropic.APIConnectionError(request=request))
    result = await llm.decide(agent_request())
    assert (result.event_type, result.reason) == ("agent.escalated", "agente indisponível")
    assert "APIConnectionError" in result.summary


async def test_refusal_escalates_as_unavailable():
    llm, _ = agent(message(stop_reason="refusal"))
    result = await llm.decide(agent_request())
    assert result.reason == "agente indisponível" and "recusa" in result.summary


async def test_running_out_of_tool_rounds_escalates():
    llm, _ = agent(("status_equipamento", {}), ("status_equipamento", {}))
    result = await llm.decide(agent_request())
    assert result.reason == "agente indisponível" and "tool_use" in result.summary


async def test_english_brand_gets_english_fallback():
    llm, _ = agent(message(stop_reason="refusal"))
    result = await llm.decide(agent_request(brand="jim", locale="en-US"))
    assert result.text.startswith("Sorry")


def test_markdown_is_stripped_for_plain_text_channels():
    assert plain("## Oi\n\n**Sua venda** cai __amanhã__.") == "Oi\nSua venda cai amanhã."


def test_user_turn_has_history_and_frustration():
    req = agent_request(history=[{"author": "customer", "text": "oi"}, {"author": "agent", "text": "olá!"}],
                        triage={"category": "payments", "priority": "normal", "frustration": 2.4},
                        locale="pt-BR")
    turn = user_turn(req)
    assert "cliente: oi\nassistente: olá!" in turn
    assert "Triagem: cliente frustrado." in turn
    assert turn.endswith(req.text)


def test_tools_data_is_stable_per_conversation():
    import asyncio
    from helpdesk.agent_llm.tools import ToolState, make_tools
    req = agent_request()
    first = asyncio.run(make_tools(req, ToolState())[0].call({"dias": 3}))
    again = asyncio.run(make_tools(req, ToolState())[0].call({"dias": 3}))
    assert first == again


def test_llm_needs_a_key():
    import pytest
    from helpdesk.config import Settings
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        LLMAgent.from_settings(Settings(agent_impl="llm", anthropic_api_key=""))
