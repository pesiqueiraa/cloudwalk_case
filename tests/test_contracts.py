import pytest
from pydantic import ValidationError

from helpdesk.contracts import AgentRequest
from tests.factories import agent_request, agent_result, chat_inbound


def test_agent_request_roundtrip():
    req = agent_request()
    assert AgentRequest.model_validate_json(req.model_dump_json()) == req


def test_chat_inbound_rejects_empty_text():
    with pytest.raises(ValidationError):
        chat_inbound(text="")


def test_agent_result_rejects_unknown_type():
    with pytest.raises(ValidationError):
        agent_result(event_type="agent.dancing")


def test_agent_request_requires_trace_id():
    data = agent_request().model_dump()
    del data["trace_id"]
    with pytest.raises(ValidationError):
        AgentRequest(**data)
