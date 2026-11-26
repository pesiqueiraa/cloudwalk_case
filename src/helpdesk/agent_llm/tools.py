"""Ferramentas do agente com LLM, sobre dados sintéticos estáveis por conversa (mesma conversa, mesmos dados).

Não há sistema real por trás: os valores saem de um gerador com semente no conversation_id, para a demo
e os testes serem repetíveis. A escalação não age aqui; só fica registrada para a política montar o
agent.escalated, que a plataforma aplica com o handoff de sempre.
"""
import json
import random
from dataclasses import dataclass, field

from anthropic import beta_async_tool

from helpdesk.contracts import AgentRequest

DEVICE = {
    "infinitepay": "Smart POS", "jim": "JIM Reader",
}
DEVICE_STATES = [
    {"bateria": "0%", "ultima_conexao": "há 3 dias", "sinal": "sem conexão"},
    {"bateria": "85%", "ultima_conexao": "há 2 minutos", "sinal": "Wi-Fi ok"},
    {"bateria": "40%", "ultima_conexao": "há 1 hora", "sinal": "chip 4G fraco"},
]


@dataclass
class ToolState:
    calls: list[str] = field(default_factory=list)
    escalation: tuple[str, str] | None = None   # (motivo, resumo)


def _rng(req: AgentRequest) -> random.Random:
    return random.Random(str(req.conversation_id))


def make_tools(req: AgentRequest, state: ToolState) -> list:
    rng = _rng(req)
    transactions = [
        {"id": f"tx-{rng.randint(100, 999)}", "tipo": "venda no crédito", "valor": round(rng.uniform(80, 900), 2),
         "status": "liquidação prevista para amanhã"},
        {"id": f"tx-{rng.randint(100, 999)}", "tipo": "Pix recebido", "valor": round(rng.uniform(20, 300), 2),
         "status": "creditado"},
    ]
    device = {"modelo": DEVICE[req.brand], **rng.choice(DEVICE_STATES)}

    @beta_async_tool
    async def consultar_transacoes(dias: int = 3) -> str:
        """Lista as transações recentes da conta do cliente, com tipo, valor e status de liquidação.

        Args:
            dias: Quantos dias para trás consultar (1 a 30).
        """
        state.calls.append(f"consultar_transacoes({dias})")
        return json.dumps(transactions, ensure_ascii=False)

    @beta_async_tool
    async def status_equipamento() -> str:
        """Mostra o status da maquininha ou do card reader do cliente: modelo, bateria, última conexão e sinal."""
        state.calls.append("status_equipamento()")
        return json.dumps(device, ensure_ascii=False)

    @beta_async_tool
    async def escalar_para_humano(motivo: str, resumo: str) -> str:
        """Transfere a conversa para um analista humano. Use quando o cliente pedir uma pessoa, houver suspeita
        de fraude ou golpe, ou as ferramentas não resolverem.

        Args:
            motivo: Motivo curto da transferência.
            resumo: Resumo do caso para o analista, em até duas frases.
        """
        state.calls.append("escalar_para_humano()")
        state.escalation = (motivo, resumo)
        return "transferência registrada"

    return [consultar_transacoes, status_equipamento, escalar_para_humano]
