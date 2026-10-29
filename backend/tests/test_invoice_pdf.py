"""Owner: Wesley (testing). Invoice PDF generation → upload → extraction → matching."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.ai.extractor import extract_invoice
from app.main import app
from app.services.invoice_pdf import invoice_from_po, render_invoice_pdf

client = TestClient(app)
SGD_PO = "PO-2026-0421"  # Jurong Hardware, charges GST
USD_PO = "PO-2026-0412"


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def po(number):
    return next(p for p in store.erp["purchase_orders"] if p["po_number"] == number)


def upload(pdf: bytes, name="invoice.pdf"):
    return client.post("/api/invoices/upload", files={"file": (name, pdf, "application/pdf")}).json()


@pytest.mark.parametrize("number", [SGD_PO, USD_PO])
def test_extractor_reads_generated_pdf(number):
    inv = invoice_from_po(po(number))
    draft = extract_invoice("x.pdf", render_invoice_pdf(inv))
    assert draft["confidence"] == 1.0
    for key in ("invoice_number", "po_number", "supplier", "invoice_date", "currency", "tax_rate", "tax_amount"):
        assert draft[key] == inv[key], key
    assert [(l["sku"], l["qty"], l["unit_price"]) for l in draft["lines"]] == [
        (l["sku"], l["qty"], l["unit_price"]) for l in inv["lines"]
    ]


def test_pdf_download():
    res = client.get(f"/api/purchase-orders/{SGD_PO}/invoice.pdf?variant=price")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")
    assert client.get("/api/purchase-orders/NOPE/invoice.pdf").status_code == 404
    assert client.get(f"/api/purchase-orders/{SGD_PO}/invoice.pdf?variant=bogus").status_code == 422


@pytest.mark.parametrize(
    "variant,status,flag",
    [
        ("clean", "matched", None),
        ("price", "review", "unit price +5.0% vs PO"),
        ("qty", "mismatch", "billed 132, PO only 120"),
        ("tax", "mismatch", "Tax should be"),
    ],
)
def test_upload_adds_to_queue_with_match(variant, status, flag):
    pdf = client.get(f"/api/purchase-orders/{SGD_PO}/invoice.pdf?variant={variant}").content
    before = len(client.get("/api/invoices").json())
    body = upload(pdf)
    assert body["invoice"]["match"]["status"] == status
    if flag:
        assert any(flag in f["message"] for f in body["invoice"]["match"]["flags"])
    assert len(client.get("/api/invoices").json()) == before + 1


def test_reupload_is_flagged_duplicate():
    pdf = client.get(f"/api/purchase-orders/{USD_PO}/invoice.pdf").content
    assert upload(pdf)["invoice"]["match"]["status"] == "matched"
    flags = upload(pdf)["invoice"]["match"]["flags"]
    assert any("duplicate" in f["message"] for f in flags)


def test_non_pdf_stays_a_draft():
    body = client.post("/api/invoices/upload", files={"file": ("scan.png", b"\x89PNG....", "image/png")}).json()
    assert body["invoice"] is None
    assert body["draft"]["confidence"] == 0.0
