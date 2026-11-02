from helpdesk.agent_mock.policy import SUMMARY_MAX, decide
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


def test_does_not_escalate_on_partial_word():
    for text in ("I booked with a travel agency", "Your agents are great", "A chemical reagent spilled"):
        result = decide(agent_request(brand="jim", locale="en-US", text=text))
        assert result.event_type == "agent.replied", text


def test_escalation_has_deterministic_summary():
    req = agent_request(customer_name="Ana", channel="whatsapp", text="Quero falar com um atendente")
    result = decide(req)
    assert result.summary == "Ana (whatsapp) pediu atendimento humano. Última mensagem: “Quero falar com um atendente”"
    assert decide(req).summary == result.summary


def test_summary_in_english():
    result = decide(agent_request(brand="jim", locale="en-US", customer_name="John", text="I want a human"))
    assert result.summary == "John (chat) asked for a human. Last message: “I want a human”"


def test_long_summary_is_clipped():
    result = decide(agent_request(text="Quero falar com um atendente. " + "Blá " * 500))
    assert len(result.summary) == SUMMARY_MAX
    assert result.summary.endswith("…”")


def test_reply_has_no_summary():
    assert decide(agent_request()).summary is None
