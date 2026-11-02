from uuid import UUID

import pytest

from helpdesk.platform.routing import route

IP_DEFAULT = UUID("10000000-0000-0000-0000-000000000001")
IP_PAYMENTS = UUID("10000000-0000-0000-0000-000000000002")
JIM_PAYMENTS = UUID("10000000-0000-0000-0000-000000000012")


def make_queue(db, name, brand="infinitepay", first_responder="agent", active=True):
    return db.execute(
        "INSERT INTO queues (name, brand_id, team_id, first_responder, active) "
        "VALUES (%s, %s, 'geral', %s, %s) RETURNING id",
        (name, brand, first_responder, active),
    ).fetchone()["id"]


def make_rule(db, queue_id, position, active=True, **conditions):
    return db.execute(
        "INSERT INTO routing_rules (name, position, brand_id, channel, category, priority, queue_id, active) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (f"regra {position}", position, conditions.get("brand"), conditions.get("channel"),
         conditions.get("category"), conditions.get("priority"), queue_id, active),
    ).fetchone()["id"]


def ip_route(db, category="payments", channel="chat", priority="normal"):
    return route(db, brand="infinitepay", channel=channel, category=category, priority=priority)


def test_seed_rule_matches_by_category(db):
    result = ip_route(db)
    assert (result.queue_id, result.matched_by, result.first_responder) == (IP_PAYMENTS, "rule", "agent")
    assert result.rule["name"] == "InfinitePay: pagamentos"
    assert result.rule["category"] == "payments"


def test_null_condition_matches_any_value(db):
    queue = make_queue(db, "Tudo do WhatsApp")
    make_rule(db, queue, position=1, channel="whatsapp")
    assert ip_route(db, channel="whatsapp").queue_id == queue
    assert ip_route(db, category="hardware", channel="whatsapp").queue_id == queue
    assert ip_route(db, channel="chat").queue_id == IP_PAYMENTS


def test_lowest_position_wins(db):
    first, second = make_queue(db, "Primeira"), make_queue(db, "Segunda")
    make_rule(db, second, position=2, category="payments")
    make_rule(db, first, position=1, category="payments")
    assert ip_route(db).queue_id == first


def test_all_conditions_must_match(db):
    queue = make_queue(db, "Pagamentos urgentes")
    make_rule(db, queue, position=1, category="payments", priority="high")
    assert ip_route(db, priority="high").queue_id == queue
    assert ip_route(db, priority="normal").queue_id == IP_PAYMENTS


def test_inactive_rule_is_ignored(db):
    queue = make_queue(db, "Regra desligada")
    make_rule(db, queue, position=1, active=False)
    assert ip_route(db).queue_id == IP_PAYMENTS


def test_rule_pointing_to_inactive_queue_is_ignored(db):
    queue = make_queue(db, "Fila desligada", active=False)
    make_rule(db, queue, position=1)
    assert ip_route(db).queue_id == IP_PAYMENTS


def test_rule_pointing_to_other_brand_queue_is_ignored(db):
    make_rule(db, JIM_PAYMENTS, position=1)
    assert ip_route(db).queue_id == IP_PAYMENTS


def test_falls_back_to_brand_default_queue(db):
    result = ip_route(db, category="account")
    assert (result.queue_id, result.matched_by, result.rule) == (IP_DEFAULT, "default", None)
    assert result.queue_name == "InfinitePay · Geral"


def test_human_queue_reports_first_responder(db):
    assert ip_route(db, category="fraud", priority="high").first_responder == "human"
