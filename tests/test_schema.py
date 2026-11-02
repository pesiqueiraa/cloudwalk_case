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
