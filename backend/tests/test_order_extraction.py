"""Customer PO PDF -> extracted order -> checked -> Koda entry record."""
import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

from app import store
from app.ai.extractor import extract_order, normalize_date
from app.main import app
from app.services.orders import koda_entry

client = TestClient(app)


def po_pdf(lines=None, delivery="2026-11-06", order_no="Purchase Order No: CPO-7781") -> bytes:
    lines = lines if lines is not None else [
        "LAP-TP-X1 ThinkPad X1 Carbon Gen 12 4 2150.00 8600.00",
        "MON-DL-27 Dell UltraSharp 27 4 489.00 1956.00",
    ]
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    rows = ["Tampines Polyclinic IT", order_no, "Order Date: 2026-10-21", f"Delivery Date: {delivery}" if delivery else "",
            "Currency: SGD", "", *lines, "Total: 10556.00"]
    for row in rows:
        pdf.cell(0, 7, row, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def test_extracts_customer_product_quantity_and_delivery_date():
    order = extract_order("po.pdf", po_pdf())
    assert order["counterparty"] == "Tampines Polyclinic IT"
    assert order["order_number"] == "CPO-7781"
    assert order["delivery_date"] == "2026-11-06"
    assert [(l["sku"], l["quantity"]) for l in order["lines"]] == [("LAP-TP-X1", 4), ("MON-DL-27", 4)]
    assert order["total"] == 10556.0
    assert order["confidence"] == 1.0 and order["missing"] == []


def test_missing_delivery_date_is_reported():
    order = extract_order("po.pdf", po_pdf(delivery=None))
    assert "delivery_date" in order["missing"]
    assert order["confidence"] < 1.0


def test_scan_without_text_layer_is_not_guessed():
    order = extract_order("scan.png", b"\x89PNG not a pdf")
    assert order["lines"] == [] and order["confidence"] == 0.0


@pytest.mark.parametrize("raw,iso", [("2026-11-06", "2026-11-06"), ("06/11/2026", "2026-11-06"),
                                     ("6 Nov 2026", "2026-11-06"), ("next week", None), (None, None)])
def test_normalize_date(raw, iso):
    assert normalize_date(raw) == iso


def test_upload_returns_validation_for_the_draft():
    res = client.post("/api/orders/upload", files={"file": ("po.pdf", po_pdf(), "application/pdf")})
    body = res.json()
    assert body["draft"]["order_number"] == "CPO-7781"
    # Unit price on the PO differs from the catalogue for neither line, but the total must reconcile.
    assert "Order total" not in " ".join(body["validation"]["issues"])


def test_upload_flags_missing_data():
    res = client.post("/api/orders/upload", files={"file": ("po.pdf", po_pdf(delivery=None), "application/pdf")})
    assert "Missing delivery date" in res.json()["validation"]["issues"]


def test_koda_entry_is_normalised_and_gated_on_validation():
    order = store.orders["orders"][0]
    entry = koda_entry(order, store.orders["catalog"])
    assert entry["record"]["customer_po"] == order["order_number"]
    assert entry["record"]["lines"][0]["item_no"] == order["lines"][0]["sku"]
    broken = koda_entry({**order, "delivery_date": None}, store.orders["catalog"])
    assert broken["ready"] is False and "Missing delivery date" in broken["issues"]


def test_koda_entry_endpoint():
    first = client.get("/api/orders").json()[0]
    res = client.get(f"/api/orders/{first['id']}/koda-entry")
    assert res.status_code == 200 and "record" in res.json()
    assert client.get("/api/orders/nope/koda-entry").status_code == 404
