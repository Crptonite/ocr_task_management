"""Tests for Aeric's 6a (Part 1) PO Intake, fuzzy SKU matching, validation & clarification email."""
import io

from fastapi.testclient import TestClient
from fpdf import FPDF

from app import store
from app.ai import llm
from app.ai import po_parser
from app.main import app
from app.services.po_intake import SAMPLES

client = TestClient(app)


def _make_pdf(text: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.replace("—", "-").strip().splitlines():
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def test_samples_endpoint_returns_demo_pos():
    store.reset()
    res = client.get("/api/po-intake/samples")
    assert res.status_code == 200
    ids = {s["id"] for s in res.json()}
    assert {"clean", "missing", "typo", "email", "csv"} <= ids


def test_clean_multi_sku_po_and_submit():
    store.reset()
    res = client.post("/api/po-intake", data={"text": SAMPLES["clean"]["text"]})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ready"
    assert body["can_submit"] is True
    assert body["meta"]["ai_used"] is False
    assert body["meta"]["tokens"] == 0
    assert body["summary"]["lines"] == 5
    assert body["summary"]["exact"] == 5
    assert body["po"]["port"] == "Los Angeles, USA"

    sub = client.post("/api/po-intake/submit", json={**body["po"], "created_by": "Aeric", "source": "Pottery Barn"})
    assert sub.status_code == 201
    order = sub.json()["order"]
    assert order["order_number"] == "PB-2026-44718"
    assert len(order["lines"]) == 5
    assert order["status"] == "extracted"
    store.reset()


def test_csv_and_pdf_po_parse_without_ai():
    store.reset()
    csv_bytes = SAMPLES["csv"]["text"].encode("utf-8")
    r_csv = client.post("/api/po-intake", files={"file": ("west_elm.csv", csv_bytes, "text/csv")})
    assert r_csv.status_code == 200
    assert r_csv.json()["status"] == "ready"
    assert r_csv.json()["meta"]["input"] == "csv"
    assert r_csv.json()["meta"]["method"] == "rules"
    assert r_csv.json()["summary"]["lines"] == 4

    pdf_bytes = _make_pdf(SAMPLES["clean"]["text"])
    r_pdf = client.post("/api/po-intake", files={"file": ("pb_po.pdf", pdf_bytes, "application/pdf")})
    assert r_pdf.status_code == 200
    assert r_pdf.json()["status"] == "ready"
    assert r_pdf.json()["meta"]["input"] == "pdf-text"
    assert r_pdf.json()["summary"]["exact"] == 5


def test_missing_port_and_delivery_date_blocks_submit_and_drafts_email():
    store.reset()
    res = client.post("/api/po-intake", data={"text": SAMPLES["missing"]["text"]})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "needs_attention"
    assert body["can_submit"] is False
    assert body["fields"]["port"]["state"] == "missing"
    assert body["fields"]["delivery_date"]["state"] == "missing"

    # Blocking error prevents queuing
    blocked = client.post("/api/po-intake/submit", json=body["po"])
    assert blocked.status_code == 409

    # Clarification email lists exact missing fields
    email_res = client.post("/api/po-intake/email", json=body["po"])
    assert email_res.status_code == 200
    mail = email_res.json()
    assert "Port of destination" in mail["body"]
    assert "Delivery date" in mail["body"]
    assert mail["to"] == "orders@crateandbarrel.example"
    assert mail["mailto"].startswith("mailto:")


def test_one_digit_sku_typo_suggests_fix_and_revalidates():
    store.reset()
    res = client.post("/api/po-intake", data={"text": SAMPLES["typo"]["text"]})
    assert res.status_code == 200
    body = res.json()
    assert body["can_submit"] is False
    assert body["lines"][0]["match"]["status"] == "typo"
    assert body["lines"][0]["match"]["suggested_sku"] == "KD-CH-2047"
    assert body["lines"][2]["match"]["status"] == "typo"
    assert body["lines"][2]["match"]["suggested_sku"] == "KD-SB-4402"

    # Clarification email names both mismatched SKUs and suggestions
    mail = client.post("/api/po-intake/email", json=body["po"]).json()
    assert "KD-CH-2041" in mail["body"] and "KD-CH-2047" in mail["body"]
    assert "KD-SB-4403" in mail["body"] and "KD-SB-4402" in mail["body"]

    # Accept the suggested SKUs and re-validate
    edited = {**body["po"], "lines": list(body["po"]["lines"])}
    edited["lines"][0] = {**edited["lines"][0], "sku": body["lines"][0]["match"]["suggested_sku"]}
    edited["lines"][2] = {**edited["lines"][2], "sku": body["lines"][2]["match"]["suggested_sku"]}
    recheck = client.post("/api/po-intake/validate", json=edited)
    assert recheck.status_code == 200
    assert recheck.json()["status"] == "ready"
    assert recheck.json()["can_submit"] is True


def test_hybrid_ai_fallback_keeps_deterministic_fields(monkeypatch):
    store.reset()
    monkeypatch.setattr(llm, "api_key", lambda: "test-key")
    monkeypatch.setattr(
        po_parser,
        "_ai_read",
        lambda filename, content, text: {
            "tokens": 312,
            "po": {
                "po_number": "AI-OVERRIDE-IGNORE",
                "buyer": "RH",
                "buyer_email": "buyer@rh.example",
                "port": "Oakland, USA",
                "order_date": "2026-11-09",
                "delivery_date": "2027-01-30",
                "currency": "USD",
                "lines": [{"sku": "KD-LC-7105", "description": "Linden lounge chair", "quantity": 10, "unit_price": 540.0, "amount": 5400.0}],
            },
        },
    )
    # Messy text has PO Number & Buyer only (no lines) -> triggers hybrid fallback without overwriting rules
    res = client.post("/api/po-intake", data={"text": "PO Number: RH-9001\nBuyer: RH Home"})
    assert res.status_code == 200
    body = res.json()
    assert body["meta"]["method"] == "hybrid"
    assert body["meta"]["ai_used"] is True
    assert body["meta"]["tokens"] == 312
    assert body["po"]["po_number"] == "RH-9001"
    assert body["po"]["port"] == "Oakland, USA"
    assert body["status"] == "ready"


def test_upload_error_handling():
    assert client.post("/api/po-intake").status_code == 400
    assert client.post("/api/po-intake", files={"file": ("bad.exe", b"mz", "application/octet-stream")}).status_code == 415
    assert client.post("/api/po-intake", files={"file": ("empty.txt", b"", "text/plain")}).status_code == 400
    assert client.post("/api/po-intake", files={"file": ("fake.pdf", b"not-a-pdf", "application/pdf")}).status_code == 415
