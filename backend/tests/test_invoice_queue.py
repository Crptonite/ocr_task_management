"""Order approval / rejection and the Review Invoice Queue."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def ready_order():
    return next(o for o in client.get("/api/orders").json()
                if o["validation"]["status"] == "ready" and o["status"] == "extracted")


def test_approve_records_admin_and_queues_invoice():
    o = ready_order()
    res = client.post(f"/api/orders/{o['id']}/approve", json={"approved_by": "Aeric"}).json()
    assert res["status"] == "approved"
    assert res["approval"]["by"] == "Aeric" and res["approval"]["at"]
    queue = client.get("/api/invoice-queue?status=pending").json()
    entry = next(e for e in queue if e["order_id"] == o["id"])
    assert entry["transaction_id"].startswith("TXN-")
    assert entry["invoice"]["subtotal"] == round(sum(l["amount"] for l in o["lines"]), 2)
    assert entry["invoice"]["total"] == round(entry["invoice"]["subtotal"] + entry["invoice"]["tax"], 2)


def test_unapproved_orders_are_not_in_queue():
    assert client.get("/api/invoice-queue").json() == []


def test_rejected_order_never_reaches_invoice_queue():
    o = ready_order()
    res = client.post(f"/api/orders/{o['id']}/reject", json={"rejected_by": "Aeric", "reason": "Credit hold"}).json()
    assert res["status"] == "rejected" and res["approval"]["reason"] == "Credit hold"
    assert client.post(f"/api/orders/{o['id']}/approve").status_code == 409
    assert client.get(f"/api/invoice-queue/{o['id']}").status_code == 404
    assert o["order_number"] not in client.get("/api/orders/export.csv").text


def test_edit_items_recalculates_and_generate_locks():
    o = ready_order()
    client.post(f"/api/orders/{o['id']}/approve")
    items = [{"name": "Widget", "description": "Blue", "quantity": 3, "unit_price": 10},
             {"name": "Installation", "quantity": 1, "unit_price": 50}]
    res = client.put(f"/api/invoice-queue/{o['id']}", json={"items": items, "tax_rate": 0.1, "edited_by": "Lucas"}).json()
    inv = res["invoice"]
    assert [i["amount"] for i in inv["items"]] == [30, 50]
    assert (inv["subtotal"], inv["tax"], inv["total"]) == (80, 8, 88)
    assert inv["updated_by"] == "Lucas"

    assert client.get(f"/api/invoice-queue/{o['id']}/invoice.pdf").status_code == 409
    gen = client.post(f"/api/invoice-queue/{o['id']}/generate", json={"generated_by": "Lucas"}).json()
    assert gen["invoice"]["status"] == "generated"
    assert client.put(f"/api/invoice-queue/{o['id']}", json={"tax_rate": 0}).status_code == 409
    pdf = client.get(f"/api/invoice-queue/{o['id']}/invoice.pdf")
    assert pdf.content.startswith(b"%PDF")
    assert all(e["order_id"] != o["id"] for e in client.get("/api/invoice-queue?status=pending").json())


def test_invalid_edits_rejected():
    o = ready_order()
    client.post(f"/api/orders/{o['id']}/approve")
    assert client.put(f"/api/invoice-queue/{o['id']}", json={"items": []}).status_code == 422
    assert client.put(f"/api/invoice-queue/{o['id']}", json={"items": [{"name": "X", "quantity": 0, "unit_price": 1}]}).status_code == 422


def test_recalculate_preview():
    res = client.post("/api/invoice-queue/recalculate", json={"items": [{"name": "A", "quantity": 2, "unit_price": 5}], "tax_rate": 0.09}).json()
    assert (res["subtotal"], res["tax"], res["total"]) == (10, 0.9, 10.9)
