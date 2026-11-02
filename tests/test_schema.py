import psycopg
import pytest

from helpdesk.platform.db import apply_schema


def test_seed_has_one_active_default_queue_per_brand(db):
    apply_schema(db)
    rows = db.execute(
        "SELECT brand_id, count(*) AS n FROM queues WHERE is_default AND active GROUP BY brand_id ORDER BY brand_id"
    ).fetchall()
    assert rows == [{"brand_id": "infinitepay", "n": 1}, {"brand_id": "jim", "n": 1}]


def test_seed_does_not_resurrect_deactivated_queue(db):
    queue_id = db.execute("SELECT id FROM queues WHERE NOT is_default LIMIT 1").fetchone()["id"]
    db.execute("UPDATE queues SET active = false, name = 'Renomeada' WHERE id = %s", (queue_id,))
    apply_schema(db)
    queue = db.execute("SELECT name, active FROM queues WHERE id = %s", (queue_id,)).fetchone()
    assert queue == {"name": "Renomeada", "active": False}


def test_only_one_active_default_queue_per_brand(db):
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(
            "INSERT INTO queues (name, brand_id, team_id, first_responder, is_default) "
            "VALUES ('Outra padrão', 'jim', 'geral', 'agent', true)"
        )


def test_seed_rules_point_to_queues_of_the_same_brand(db):
    mismatched = db.execute(
        "SELECT count(*) AS n FROM routing_rules r JOIN queues q ON q.id = r.queue_id "
        "WHERE r.brand_id IS DISTINCT FROM q.brand_id"
    ).fetchone()["n"]
    assert mismatched == 0


def test_schema_upgrade_adds_columns_to_week1_tables(db):
    db.execute("DROP SCHEMA public CASCADE")
    db.execute("CREATE SCHEMA public")
    # Formato da semana 1, sem as colunas novas
    db.execute("""
        CREATE TABLE brands (id text PRIMARY KEY, name text NOT NULL, locale text NOT NULL);
        CREATE TABLE conversations (id uuid PRIMARY KEY, brand_id text NOT NULL, customer_id uuid NOT NULL,
            channel text NOT NULL, external_session_id text NOT NULL, status text NOT NULL DEFAULT 'open');
        CREATE TABLE messages (id uuid PRIMARY KEY, conversation_id uuid NOT NULL, trace_id uuid NOT NULL,
            direction text NOT NULL, author text NOT NULL, text text NOT NULL);
    """)
    apply_schema(db)
    columns = {
        (r["table_name"], r["column_name"]) for r in db.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_name IN ('conversations', 'messages')"
        ).fetchall()
    }
    for column in ("queue_id", "priority", "handled_by", "routed_at"):
        assert ("conversations", column) in columns
    for column in ("category", "priority"):
        assert ("messages", column) in columns


def test_schema_upgrade_from_week2_keeps_data_and_relaxes_uniqueness(db):
    db.execute("DROP SCHEMA public CASCADE")
    db.execute("CREATE SCHEMA public")
    # Formato da semana 2: conversa única por sessão e jobs sem 'cancelled'
    db.execute("""
        CREATE TABLE brands (id text PRIMARY KEY, name text NOT NULL, locale text NOT NULL);
        CREATE TABLE conversations (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), brand_id text NOT NULL,
            customer_id uuid NOT NULL, channel text NOT NULL, external_session_id text NOT NULL,
            status text NOT NULL DEFAULT 'open', UNIQUE (brand_id, channel, external_session_id));
        CREATE TABLE webhook_jobs (id bigserial PRIMARY KEY, event_id uuid NOT NULL UNIQUE, trace_id uuid NOT NULL,
            conversation_id uuid NOT NULL, payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
            attempts int NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(), last_error text);
        INSERT INTO conversations (brand_id, customer_id, channel, external_session_id)
            VALUES ('jim', gen_random_uuid(), 'chat', 's-1');
    """)
    apply_schema(db)
    apply_schema(db)  # idempotente

    db.execute("UPDATE conversations SET status = 'closed'")
    db.execute("INSERT INTO conversations (brand_id, customer_id, channel, external_session_id) "
               "VALUES ('jim', gen_random_uuid(), 'chat', 's-1')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute("INSERT INTO conversations (brand_id, customer_id, channel, external_session_id) "
                   "VALUES ('jim', gen_random_uuid(), 'chat', 's-1')")


def test_job_status_accepts_cancelled_and_rejects_unknown(db):
    insert = ("INSERT INTO webhook_jobs (event_id, trace_id, conversation_id, payload, status) "
              "VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), '{}', %s)")
    db.execute(insert, ("cancelled",))
    with pytest.raises(psycopg.errors.CheckViolation):
        db.execute(insert, ("lost",))
