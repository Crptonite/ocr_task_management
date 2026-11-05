"""OpenAI fallback: used for scans and unreadable layouts, never required."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.ai import llm
from app.ai.extractor import extract_invoice, extract_order
from app.main import app
from tests.test_order_extraction import po_pdf

client = TestClient(app)

SCAN = b"\x89PNG fake scan"
READ_ORDER = {
    "order_number": "CPO-9", "counterparty": "Tampines Polyclinic IT", "order_date": "2026-10-21",
    "delivery_date": "6 Nov 2026", "currency": "SGD", "total": 8600.0,
    "lines": [{"sku": "LAP-TP-X1", "description": "ThinkPad", "quantity": 4, "unit_price": 2150.0, "amount": 8600.0}],
}
READ_INVOICE = {
    "invoice_number": "HHE-1", "po_number": "PO-2026-0412", "supplier": "Hanoi Hardwood Exports",
    "invoice_date": "2026-10-19", "currency": "USD", "tax_rate": 0.0, "tax_amount": 0.0,
    "lines": [{"sku": "BIR-PNL-18", "description": "Birch", "qty": 220, "unit_price": 21.9}],
}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(llm, "api_key", lambda: "sk-test")


def test_scan_is_read_by_openai_when_key_is_set(key, monkeypatch):
    monkeypatch.setattr(llm, "read_order", lambda name, content: READ_ORDER)
    order = extract_order("scan.png", SCAN)
    assert order["order_number"] == "CPO-9"
    assert order["delivery_date"] == "2026-11-06"  # normalised to ISO
    assert order["confidence"] == 1.0 and "OpenAI" in order["note"]


def test_scan_invoice_goes_through_matching(key, monkeypatch):
    monkeypatch.setattr(llm, "read_invoice", lambda name, content: READ_INVOICE)
    draft = extract_invoice("scan.png", SCAN)
    assert draft["confidence"] == 1.0 and draft["supplier"] == "Hanoi Hardwood Exports"


def test_complete_regex_read_does_not_call_openai(key, monkeypatch):
    def boom(*a):
        raise AssertionError("OpenAI should not be called")
    monkeypatch.setattr(llm, "read_order", boom)
    assert extract_order("po.pdf", po_pdf())["confidence"] == 1.0


def test_incomplete_pdf_falls_back_to_openai(key, monkeypatch):
    monkeypatch.setattr(llm, "read_order", lambda name, content: READ_ORDER)
    order = extract_order("po.pdf", po_pdf(delivery=None))
    assert order["delivery_date"] == "2026-11-06" and order["missing"] == []


def test_openai_failure_keeps_regex_result(key, monkeypatch):
    def fail(*a):
        raise RuntimeError("quota")
    monkeypatch.setattr(llm, "read_order", fail)
    order = extract_order("po.pdf", po_pdf(delivery=None))
    assert "delivery_date" in order["missing"] and "OpenAI read failed" in order["note"]


def test_scan_without_key_says_how_to_enable():
    order = extract_order("scan.png", SCAN)
    assert order["confidence"] == 0.0 and "OPENAI_API_KEY" in order["note"]


def test_upload_endpoint_uses_openai_for_scans(key, monkeypatch):
    monkeypatch.setattr(llm, "read_invoice", lambda name, content: {**READ_INVOICE, "lines": [
        {"sku": "BIR-PNL-18", "description": "Birch", "qty": 300, "unit_price": 21.9}]})
    body = client.post("/api/invoices/upload", files={"file": ("scan.png", SCAN, "image/png")}).json()
    flags = [f["message"] for f in body["invoice"]["match"]["flags"]]
    assert any("billed 300, PO only 220" in f for f in flags)
