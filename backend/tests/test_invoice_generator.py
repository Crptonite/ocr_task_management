from fastapi.testclient import TestClient
from pypdf import PdfReader
from io import BytesIO

from app.main import app

client = TestClient(app)

PAYLOAD = {
    "invoice_number": "PO-2026-0141", "seller": "Hafele Hardware Asia", "buyer": "Buyer name",
    "issue_date": "2026-10-23", "service_date": "2026-10-31", "payment_method": "Wire transfer",
    "payment_date": "2026-11-06", "currency": "SGD", "gst_rate": 0.09,
    "items": [{"description": "Hinge", "quantity": 10, "unit_price": 2.5}, {"description": "Handle", "quantity": 2, "unit_price": 12.5}],
}


def test_totals_include_gst():
    t = client.post("/api/invoice-generator/totals", json=PAYLOAD).json()
    assert (t["subtotal"], t["gst"], t["total"]) == (50.0, 4.5, 54.5)


def test_pdf_contains_details():
    r = client.post("/api/invoice-generator/pdf", json=PAYLOAD)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = PdfReader(BytesIO(r.content)).pages[0].extract_text()
    for s in ("Hafele Hardware Asia", "PO-2026-0141", "Wire transfer", "2026-11-06", "$54.50"):
        assert s in text


def test_rejects_empty_items():
    assert client.post("/api/invoice-generator/pdf", json={**PAYLOAD, "items": []}).status_code == 422
