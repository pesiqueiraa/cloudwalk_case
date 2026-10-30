from helpdesk.agent_mock.policy import decide
from tests.factories import agent_request


def test_replies_in_portuguese_for_infinitepay():
    result = decide(agent_request(customer_name="Ana"))
    assert result.event_type == "agent.replied"
    assert result.text.startswith("Olá, Ana!")
    assert result.reason is None


def test_replies_in_english_for_jim():
    result = decide(agent_request(brand="jim", locale="en-US", customer_name="John",
                                  text="My card reader is off"))
    assert result.event_type == "agent.replied"
    assert result.text.startswith("Hi John!")


def test_escalates_when_customer_asks_for_human():
    result = decide(agent_request(text="Quero falar com um ATENDENTE agora"))
    assert result.event_type == "agent.escalated"
    assert result.reason == "cliente pediu atendimento humano"


def test_escalates_in_english():
    result = decide(agent_request(brand="jim", locale="en-US", text="I want a human, please"))
    assert result.event_type == "agent.escalated"
    assert result.reason == "customer asked for a human"


def test_same_request_gives_same_event_id():
    req = agent_request()
    assert decide(req).event_id == decide(req).event_id
    assert decide(req).event_id != decide(agent_request()).event_id


def test_preserves_trace_and_conversation():
    req = agent_request()
    result = decide(req)
    assert (result.trace_id, result.conversation_id, result.in_reply_to) == (
        req.trace_id, req.conversation_id, req.message_id)
