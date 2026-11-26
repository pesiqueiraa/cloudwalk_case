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


# Campos opcionais de 25/11: schema_version continua 1 e payloads antigos continuam válidos

def test_old_agent_request_without_history_still_validates():
    payload = agent_request().model_dump(mode="json")
    payload.pop("history"), payload.pop("triage")
    req = AgentRequest.model_validate(payload)
    assert (req.history, req.triage, req.schema_version) == ([], None, 1)


def test_history_is_capped():
    with pytest.raises(ValidationError):
        agent_request(history=[{"author": "customer", "text": f"m{i}"} for i in range(11)])


def test_agent_result_may_say_who_answered():
    result = agent_result(agent={"impl": "llm", "model": "claude-sonnet-5-5", "effort": "low", "prompt_version": "1"})
    assert result.agent.model == "claude-sonnet-5-5"
    assert agent_result().agent is None
