"""Conversão entre os contratos e os registros Kafka."""
from typing import TypeVar

from pydantic import BaseModel

from helpdesk.contracts import AgentRequest, AgentResult

T = TypeVar("T", bound=BaseModel)

Record = tuple[bytes, bytes, list[tuple[str, bytes]]]


def to_record(model: AgentRequest | AgentResult) -> Record:
    """Chave = conversation_id, para que as mensagens de uma conversa fiquem na mesma partição."""
    key = str(model.conversation_id).encode()
    value = model.model_dump_json().encode()
    headers = [("trace_id", str(model.trace_id).encode())]
    return key, value, headers


def from_record(value: bytes, model: type[T]) -> T:
    return model.model_validate_json(value)
