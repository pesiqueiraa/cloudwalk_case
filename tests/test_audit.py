from uuid import uuid4

import psycopg
import pytest

from helpdesk.platform import audit
from helpdesk.platform.db import apply_schema


def test_record_and_list_by_trace(db):
    trace_id, conversation_id = uuid4(), uuid4()
    audit.record(db, type="message.received", trace_id=trace_id, conversation_id=conversation_id,
                 actor="platform", payload={"channel": "chat"})
    audit.record(db, type="message.sent_to_agent", trace_id=trace_id, conversation_id=conversation_id,
                 actor="platform-worker", payload={"attempt": 1})
    audit.record(db, type="message.received", trace_id=uuid4(), conversation_id=uuid4(),
                 actor="platform", payload={})

    events = audit.list_by_trace(db, trace_id)

    assert [e["type"] for e in events] == ["message.received", "message.sent_to_agent"]
    assert events[0]["payload"] == {"channel": "chat"}


def test_list_by_conversation(db):
    conversation_id = uuid4()
    audit.record(db, type="message.received", trace_id=uuid4(), conversation_id=conversation_id,
                 actor="platform", payload={})
    assert len(audit.list_by_conversation(db, conversation_id)) == 1


def test_audit_is_append_only(db):
    audit.record(db, type="message.received", trace_id=uuid4(), conversation_id=uuid4(),
                 actor="platform", payload={})
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("UPDATE audit_events SET type = 'x'")
    with pytest.raises(psycopg.errors.RaiseException):
        db.execute("DELETE FROM audit_events")


def test_apply_schema_is_idempotent(db):
    apply_schema(db)
    rows = db.execute("SELECT id, locale FROM brands ORDER BY id").fetchall()
    assert rows == [{"id": "infinitepay", "locale": "pt-BR"}, {"id": "jim", "locale": "en-US"}]
