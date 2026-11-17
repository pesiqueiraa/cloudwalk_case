from helpdesk.agent_mock.policy import ESCALATION_TERMS
from helpdesk.simulator.chaos import agent_texts, analyze, from_k6_lines, k6_pool, percentile


def event(type_, at):
    return {"type": type_, "occurred_at": f"2026-11-02T10:00:{at:06.3f}+00:00"}


def reply(trace):
    return {"author": "agent", "trace_id": trace}


def sent(*items):
    return [{"trace_id": t, "conversation_id": c, "seq": i} for i, (t, c) in enumerate(items)]


HAPPY = [event("message.received", 0), event("message.sent_to_agent", 0.2), event("agent.replied", 0.5)]


def test_all_answered_once_is_ok():
    report = analyze(sent(("t1", "c1"), ("t2", "c1")), {"t1": HAPPY, "t2": HAPPY},
                     {"c1": [reply("t1"), reply("t2")]})
    assert report.ok
    assert report.latencies_s == [0.5, 0.5]


def test_missing_reply_is_lost():
    report = analyze(sent(("t1", "c1")), {"t1": HAPPY[:2]}, {"c1": []})
    assert report.lost == ["t1"] and not report.ok


def test_two_agent_messages_is_duplicate():
    report = analyze(sent(("t1", "c1")), {"t1": HAPPY}, {"c1": [reply("t1"), reply("t1")]})
    assert report.duplicated == ["t1"]


def test_resent_webhook_is_counted_but_ok():
    events = HAPPY + [event("message.sent_to_agent", 1)]
    report = analyze(sent(("t1", "c1")), {"t1": events}, {"c1": [reply("t1")]})
    assert report.ok and report.resent_webhooks == 1


def test_replies_out_of_order_are_flagged():
    report = analyze(sent(("t1", "c1"), ("t2", "c1")), {"t1": HAPPY, "t2": HAPPY},
                     {"c1": [reply("t2"), reply("t1")]})
    assert report.out_of_order == ["c1"]


def test_percentile():
    values = [float(v) for v in range(1, 101)]
    assert (percentile(values, 50), percentile(values, 95), percentile(values, 100)) == (50.0, 95.0, 100.0)


def test_burst_texts_never_escalate():
    for brand, locale in (("infinitepay", "pt-BR"), ("jim", "en-US")):
        texts = agent_texts(brand)
        assert texts
        assert not any(ESCALATION_TERMS[locale].search(t) for t in texts)


def test_from_k6_lines_builds_batch_sorted_by_seq():
    lines = [
        '{"seq": 1, "trace_id": "t2", "conversation_id": "c1", "message_id": "m2", "ingest_ms": 8.5}\n',
        'linha de log do k6 que não é json\n',
        '{"seq": 0, "trace_id": "t1", "conversation_id": "c1", "message_id": "m1", "ingest_ms": 12.0}\n',
    ]
    batch = from_k6_lines(lines, rate=11)
    assert [m["trace_id"] for m in batch["messages"]] == ["t1", "t2"]
    assert batch["messages"][0]["ingest_ms"] == 12.0
    assert batch["rate"] == 11 and batch["ingest_errors"] == 0


def test_from_k6_lines_counts_rejected_ingestion():
    lines = ['{"seq": 0, "error": 503}', '{"seq": 1, "trace_id": "t2", "conversation_id": "c1", "message_id": "m2"}']
    batch = from_k6_lines(lines)
    assert batch["ingest_errors"] == 1 and len(batch["messages"]) == 1


def test_ingest_errors_fail_the_report():
    report = analyze(sent(("t1", "c1")), {"t1": HAPPY}, {"c1": [reply("t1")]})
    report.ingest_errors = 1
    assert not report.ok


def test_throughput_uses_window_from_first_received_to_last_replied():
    late = [event("message.received", 1), event("agent.replied", 2.5)]
    report = analyze(sent(("t1", "c1"), ("t2", "c2")), {"t1": HAPPY, "t2": late},
                     {"c1": [reply("t1")], "c2": [reply("t2")]})
    assert report.window_s == 2.5
    assert report.throughput == 2 / 2.5
    assert report.as_dict()["p50_s"] == 0.5


def test_k6_pool_has_only_agent_texts_and_synthetic_customers():
    pool = k6_pool("infinitepay")
    assert pool["texts"] == agent_texts("infinitepay")
    assert all(set(c) == {"external_id", "name", "email"} for c in pool["customers"])
