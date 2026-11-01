"""Material requirements, shortages and build priorities."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.services.planning import plan, requirements

client = TestClient(app)
TODAY = date(2026, 10, 29)


def data(**overrides):
    base = {
        "products": {"P": {"name": "Widget", "bom": {"A": 2, "B": 1}}},
        "materials": {"A": {"name": "Part A", "on_hand": 10, "unit": "pc"},
                      "B": {"name": "Part B", "on_hand": 100, "unit": "pc"}},
        "inbound": [],
        "demand": [{"order_number": "O1", "customer": "Acme", "product": "P", "quantity": 4, "due_date": "2026-11-05"}],
    }
    return {**base, **overrides}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def by_number(result):
    return {o["order_number"]: o for o in result["orders"]}


def test_requirements_explode_the_bom():
    order = {"product": "P", "quantity": 4}
    assert requirements(order, data()["products"]) == {"A": 8, "B": 4}


def test_order_covered_by_stock_is_ready():
    o = by_number(plan(data(), TODAY))["O1"]
    assert o["status"] == "ready" and o["shortages"] == []


def test_shortage_reports_how_much_and_when_it_is_covered():
    d = data(demand=[{"order_number": "O1", "customer": "Acme", "product": "P", "quantity": 8, "due_date": "2026-11-05"}],
             inbound=[{"po_number": "PO-1", "sku": "A", "qty": 20, "eta": "2026-11-12"}])
    o = by_number(plan(d, TODAY))["O1"]
    assert o["status"] == "short"
    assert o["shortages"][0]["sku"] == "A"
    assert o["shortages"][0]["short_by"] == 6
    assert o["shortages"][0]["covered_from"] == "2026-11-12"  # arrives after the due date
    assert o["buildable_units"] == 5


def test_inbound_before_due_date_makes_order_startable_later():
    d = data(demand=[{"order_number": "O1", "customer": "Acme", "product": "P", "quantity": 8, "due_date": "2026-11-05"}],
             inbound=[{"po_number": "PO-1", "sku": "A", "qty": 20, "eta": "2026-11-02"}])
    o = by_number(plan(d, TODAY))["O1"]
    assert o["status"] == "inbound" and o["start_after"] == "2026-11-02"


def test_blocked_order_does_not_starve_a_later_one():
    d = data(demand=[
        {"order_number": "BIG", "customer": "X", "product": "P", "quantity": 100, "due_date": "2026-11-01"},
        {"order_number": "SMALL", "customer": "Y", "product": "P", "quantity": 5, "due_date": "2026-11-09"},
    ])
    orders = by_number(plan(d, TODAY))
    assert orders["BIG"]["status"] == "short"
    assert orders["SMALL"]["status"] == "ready"


def test_earlier_due_date_gets_the_stock_first():
    d = data(demand=[
        {"order_number": "LATE", "customer": "Y", "product": "P", "quantity": 5, "due_date": "2026-11-20"},
        {"order_number": "EARLY", "customer": "X", "product": "P", "quantity": 5, "due_date": "2026-11-05"},
    ])
    orders = by_number(plan(d, TODAY))
    assert orders["EARLY"]["status"] == "ready"
    assert orders["LATE"]["status"] == "short"  # only 10 of part A, EARLY used all of it


def test_priority_levels():
    d = data(demand=[
        {"order_number": "SOON", "customer": "X", "product": "P", "quantity": 1, "due_date": "2026-10-31"},
        {"order_number": "LATER", "customer": "X", "product": "P", "quantity": 1, "due_date": "2026-12-31"},
        {"order_number": "BLOCKED", "customer": "X", "product": "P", "quantity": 50, "due_date": "2026-11-03"},
    ])
    orders = by_number(plan(d, TODAY))
    assert orders["SOON"]["priority"] == "urgent"
    assert orders["LATER"]["priority"] == "normal"
    assert orders["BLOCKED"]["priority"] == "urgent"


def test_purchase_suggestion_for_unscheduled_shortage():
    d = data(demand=[{"order_number": "O1", "customer": "Acme", "product": "P", "quantity": 8, "due_date": "2026-11-05"}])
    suggestion = plan(d, TODAY)["purchase_suggestions"][0]
    assert suggestion["sku"] == "A" and suggestion["buy_qty"] == 6 and suggestion["needed_by"] == "2026-11-05"


def test_unknown_product_is_flagged_not_crashed():
    d = data(demand=[{"order_number": "O1", "customer": "Acme", "product": "NOPE", "quantity": 1, "due_date": "2026-11-05"}])
    result = plan(d, TODAY)
    assert result["orders"][0]["status"] == "unknown_product"
    assert result["summary"]["short"] == 1


def test_sequence_puts_startable_work_before_blocked_work():
    result = plan(store.planning, TODAY)
    statuses = [s["status"] for s in result["sequence"]]
    assert statuses == sorted(statuses, key=lambda s: {"ready": 0, "inbound": 1}.get(s, 2))


def test_mock_scenario():
    result = plan(store.planning, TODAY)
    orders = by_number(result)
    assert orders["SO-K-1001"]["status"] == "ready"
    assert orders["SO-K-1003"]["status"] == "inbound"
    assert orders["SO-K-1004"]["status"] == "short"
    assert {m["sku"] for m in result["materials"] if m["status"] != "ok"} >= {"FAB-CTN-NV"}


def test_api_returns_plan_and_validates_date():
    res = client.get("/api/planning", params={"as_of": "2026-10-29"})
    assert res.status_code == 200
    assert res.json()["as_of"] == "2026-10-29"
    assert client.get("/api/planning", params={"as_of": "soon"}).status_code == 422
