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


def test_escalation_requires_reason_and_summary():
    with pytest.raises(ValidationError):
        agent_result(event_type="agent.escalated", reason="cliente pediu atendimento humano")
    with pytest.raises(ValidationError):
        agent_result(event_type="agent.escalated", summary="Ana pediu atendimento humano")
    result = agent_result(event_type="agent.escalated", reason="motivo", summary="resumo")
    assert result.summary == "resumo"


def test_reply_does_not_need_summary():
    assert agent_result().summary is None


def test_email_subject_is_limited():
    from tests.factories import email_inbound

    with pytest.raises(ValidationError):
        email_inbound(subject="S" * 201)


def test_email_subject_plus_body_fits_agent_text():
    from tests.factories import email_inbound

    # A plataforma junta "assunto\n\ncorpo" num texto só, que o AgentRequest limita a 4000
    assert email_inbound(subject="S" * 100, body_text="B" * 3898)
    with pytest.raises(ValidationError):
        email_inbound(subject="S" * 100, body_text="B" * 3899)
