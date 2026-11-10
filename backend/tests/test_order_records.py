"""Adding orders by hand and updating existing order records."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

client = TestClient(app)

NEW = {
    "order_number": "SO-90001", "counterparty": "Jurong Clinic", "order_date": "2026-11-10",
    "delivery_date": "2026-11-20", "currency": "sgd", "created_by": "Wesley",
    "lines": [
        {"description": "ThinkPad X1 Carbon Gen 12", "quantity": 2, "unit_price": 2150},
        {"sku": "CBL-C6-3M", "description": "Cat6 patch cable 3m", "quantity": 10, "unit_price": 4.2},
    ],
}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def create(**overrides):
    return client.post("/api/orders", json={**NEW, **overrides})


def test_create_order_with_multiple_items():
    before = len(client.get("/api/orders").json())
    res = create()
    assert res.status_code == 201
    o = res.json()
    assert [l["amount"] for l in o["lines"]] == [4300, 42]
    assert o["total"] == 4342
    assert o["lines"][0]["sku"] == "LAP-TP-X1"  # filled in from the catalogue name
    assert o["status"] == "extracted" and o["currency"] == "SGD" and o["transaction_id"].startswith("TXN-")
    assert o["validation"]["status"] == "ready"
    assert len(client.get("/api/orders").json()) == before + 1


@pytest.mark.parametrize("bad", [
    {"lines": []},
    {"lines": [{"description": "X", "quantity": 0, "unit_price": 1}]},
    {"lines": [{"description": "X", "quantity": 1, "unit_price": -1}]},
    {"order_number": ""},
])
def test_create_rejects_bad_input(bad):
    assert create(**bad).status_code == 422


def test_edit_updates_in_place_and_recalculates():
    o = create().json()
    count = len(client.get("/api/orders").json())
    res = client.patch(f"/api/orders/{o['id']}", json={
        "counterparty": "Jurong Medical Clinic", "updated_by": "Wesley",
        "lines": [{"description": "ThinkPad X1 Carbon Gen 12", "quantity": 3, "unit_price": 2100}],
    }).json()
    assert res["id"] == o["id"] and res["counterparty"] == "Jurong Medical Clinic"
    assert res["lines"][0]["amount"] == 6300 and res["total"] == 6300
    assert res["updated_by"] == "Wesley"
    assert len(client.get("/api/orders").json()) == count  # no duplicate record


def test_status_update_via_patch_and_reopen():
    o = create().json()
    approved = client.patch(f"/api/orders/{o['id']}", json={"status": "approved", "updated_by": "Aeric"}).json()
    assert approved["status"] == "approved" and approved["approval"]["by"] == "Aeric"
    assert client.get(f"/api/invoice-queue/{o['id']}").status_code == 200

    # Editing an approved order needs it reopened in the same request.
    assert client.patch(f"/api/orders/{o['id']}", json={"order_number": "X"}).status_code == 409
    reopened = client.patch(f"/api/orders/{o['id']}", json={"status": "extracted", "order_number": "SO-90001-A"}).json()
    assert reopened["status"] == "extracted" and reopened["order_number"] == "SO-90001-A"
    assert "approval" not in reopened
    assert client.get(f"/api/invoice-queue/{o['id']}").status_code == 404

    rejected = client.patch(f"/api/orders/{o['id']}", json={"status": "rejected", "reason": "Cancelled"}).json()
    assert rejected["status"] == "rejected" and rejected["approval"]["reason"] == "Cancelled"
    assert [h["status"] for h in rejected["status_history"]] == ["extracted", "approved", "extracted", "rejected"]


def test_invalid_approval_leaves_record_untouched():
    o = create().json()
    res = client.patch(f"/api/orders/{o['id']}", json={"status": "approved", "delivery_date": "2026-01-01"})
    assert res.status_code == 409
    assert client.get(f"/api/orders/{o['id']}").json()["delivery_date"] == "2026-11-20"


def test_cannot_reopen_after_invoice_generated():
    o = create().json()
    client.post(f"/api/orders/{o['id']}/approve")
    client.post(f"/api/invoice-queue/{o['id']}/generate")
    assert client.patch(f"/api/orders/{o['id']}", json={"status": "extracted"}).status_code == 409
