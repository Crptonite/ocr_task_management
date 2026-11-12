"""Uploads with unreadable header fields get generated values and, if needed, an auto-created PO."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.ai import llm
from app.main import app
from app.services import autofill

client = TestClient(app)

RECEIPT = {
    "invoice_number": None, "po_number": None, "supplier": None, "invoice_date": None, "currency": None,
    "tax_rate": 0.0, "tax_amount": 0.0,
    "lines": [{"sku": None, "description": "Wireless earbuds", "qty": 3, "unit_price": 52.81}],
}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


@pytest.fixture
def read_as(monkeypatch):
    monkeypatch.setattr(llm, "api_key", lambda: "sk-test")

    def use(fields):
        monkeypatch.setattr(llm, "read_invoice", lambda name, content: {**fields, "lines": [dict(l) for l in fields["lines"]]})
    return use


def upload():
    return client.post("/api/invoices/upload", files={"file": ("receipt.png", b"\x89PNG receipt", "image/png")}).json()


def test_receipt_without_header_fields_joins_the_queue(read_as):
    read_as(RECEIPT)
    inv = upload()["invoice"]
    assert inv["invoice_number"].startswith(autofill.AUTO_INVOICE_PREFIX)
    assert inv["po_number"].startswith(autofill.AUTO_PO_PREFIX)
    assert inv["supplier"] == autofill.UNKNOWN_SUPPLIER
    assert inv["currency"] == autofill.DEFAULT_CURRENCY
    assert set(inv["auto_filled"]) == {"invoice_number", "po_number", "supplier", "currency", "invoice_date"}
    # Never "matched" on its own: generated values and the new PO both need a person to check them.
    assert inv["match"]["status"] == "review"
    messages = " ".join(f["message"] for f in inv["match"]["flags"])
    assert "auto-filled" in messages and "auto-created" in messages
    assert inv["total"] == round(3 * 52.81, 2)


def test_auto_created_po_mirrors_the_invoice_lines(read_as):
    read_as(RECEIPT)
    inv = upload()["invoice"]
    po = next(p for p in client.get("/api/purchase-orders").json() if p["po_number"] == inv["po_number"])
    assert po["auto_created"] and po["source_invoice"] == inv["invoice_number"]
    assert po["lines"] == [{"sku": "AUTO-1", "description": "Wireless earbuds", "qty": 3, "unit_price": 52.81}]


def test_numbers_do_not_collide(read_as):
    read_as(RECEIPT)
    first, second = upload()["invoice"], upload()["invoice"]
    assert first["invoice_number"] != second["invoice_number"]
    assert first["po_number"] != second["po_number"]


def test_known_po_is_kept_and_no_po_is_created(read_as):
    read_as({**RECEIPT, "po_number": "PO-2026-0412", "supplier": "Hanoi Hardwood Exports", "currency": "USD"})
    before = len(store.erp["purchase_orders"])
    inv = upload()["invoice"]
    assert inv["po_number"] == "PO-2026-0412"
    assert set(inv["auto_filled"]) == {"invoice_number", "invoice_date"}
    assert len(store.erp["purchase_orders"]) == before


def test_no_line_items_stays_a_draft(read_as):
    read_as({**RECEIPT, "lines": []})
    body = upload()
    assert body["invoice"] is None and not store.erp["invoices"][3:]


def test_deleting_the_invoice_removes_its_auto_po(read_as):
    read_as(RECEIPT)
    inv = upload()["invoice"]
    assert client.delete(f"/api/invoices/{inv['invoice_number']}").status_code == 204
    assert all(p["po_number"] != inv["po_number"] for p in store.erp["purchase_orders"])


def test_restore_rebuilds_auto_po_after_restart():
    saved = {"invoice_number": "INV-AUTO-20261111-001", "po_number": "PO-AUTO-20261111-001", "supplier": "Unknown supplier",
             "currency": "SGD", "lines": [{"sku": None, "description": "Lamp", "qty": 1, "unit_price": 79.31}]}
    autofill.restore([saved])
    assert set(saved["auto_filled"]) == {"invoice_number", "po_number", "supplier"}
    assert any(p["po_number"] == "PO-AUTO-20261111-001" for p in store.erp["purchase_orders"])
