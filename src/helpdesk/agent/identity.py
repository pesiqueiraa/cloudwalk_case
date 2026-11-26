"""Identidade da resposta do agente, comum ao mock e ao LLM."""
from uuid import NAMESPACE_URL, UUID, uuid5

from helpdesk.contracts import AgentRequest


def result_event_id(req: AgentRequest) -> UUID:
    """Derivado da requisição: uma reentrega gera o mesmo event_id e a plataforma descarta a cópia.

    O prefixo "agent-mock:" é histórico e fica: mock e LLM geram o mesmo event_id para a mesma requisição,
    então só uma resposta vale, mesmo que a implementação seja trocada no meio de uma reentrega.
    """
    return uuid5(NAMESPACE_URL, f"agent-mock:{req.event_id}")
