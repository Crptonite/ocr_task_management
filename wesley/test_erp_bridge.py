"""Tests for Wesley's 6a (Part 2) SG-to-Vietnam ERP Bridge, Price Masking, Lead-Time Advisor & Navision 2013 Export."""
import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app import database, store
from app.ai import llm
from app.main import app
from app.services import documents, supabase_store
from aeric.service import SAMPLES
from wesley import service as bridge_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_wesley_tests(monkeypatch, tmp_path):
    """Mirror backend/tests/conftest.py so tests inside wesley/ stay isolated from live APIs, DBs, and repo CSV."""
    monkeypatch.setattr(llm, "api_key", lambda: None)
    monkeypatch.setattr(supabase_store, "enabled", lambda: False)
    monkeypatch.setattr(documents, "CSV_PATH", tmp_path / "documents.csv")
    monkeypatch.setenv("DATABASE_URL", "off")
    database.close()
    store.reset()
    bridge_service.reset_mappings()
    yield
    store.reset()
    bridge_service.reset_mappings()
    database.close()


def _intake_submit_and_approve(sample_key: str = "clean") -> str:
    parsed = client.post("/api/po-intake", data={"text": SAMPLES[sample_key]["text"]})
    assert parsed.status_code == 200
    po = parsed.json()["po"]
    sub = client.post("/api/po-intake/submit", json={**po, "created_by": "Aeric", "source": "Test PO"})
    assert sub.status_code == 201
    order_id = sub.json()["order"]["id"]
    app_res = client.post(f"/api/orders/{order_id}/approve", json={"approved_by": "Wesley"})
    assert app_res.status_code == 200
    return order_id


def test_end_to_end_intake_approve_bridge_convert():
    order_id = _intake_submit_and_approve("clean")

    listed = client.get("/api/erp-bridge/orders?role=sg")
    assert listed.status_code == 200
    body = listed.json()
    assert body["role"] == "sg"
    match = next(o for o in body["orders"] if o["order_id"] == order_id)
    assert match["vn_so_number"] == "VN-SO-PB-2026-44718"
    assert match["status"] == "ready"
    assert match["can_convert"] is True
    assert match["can_export"] is True
    assert len(match["lines"]) == 5
    assert match["lines"][0]["vn_item_code"] == "VN-BOM-CH2047"
    assert match["lead_time_risk"]["risk_level"] == "feasible"

    conv = client.post(
        f"/api/erp-bridge/orders/{order_id}/convert",
        json={"converted_by": "Wesley", "role": "sg", "notes": "Release to Binh Duong Plant 1"},
    )
    assert conv.status_code == 200
    conv_body = conv.json()
    assert conv_body["converted"] is True
    assert conv_body["conversion"]["converted_by"] == "Wesley"
    assert conv_body["conversion"]["vn_so_number"] == "VN-SO-PB-2026-44718"


def test_role_based_price_masking_hides_customer_prices_from_vietnam():
    order_id = _intake_submit_and_approve("clean")

    sg = client.get(f"/api/erp-bridge/orders/{order_id}?role=sg").json()
    assert sg["confidentiality_masked"] is False
    assert sg["customer_price_masked"] is False
    assert sg["customer_total"] is not None and sg["customer_total"] > 0
    assert sg["hq_margin_total"] is not None and sg["hq_margin_total"] > 0
    assert sg["lines"][0]["customer_unit_price"] == 145.0
    assert sg["lines"][0]["hq_margin"] is not None

    vn = client.get(f"/api/erp-bridge/orders/{order_id}?role=vn").json()
    assert vn["confidentiality_masked"] is True
    assert vn["customer_price_masked"] is True
    assert vn["customer_total"] is None
    assert vn["hq_margin_total"] is None
    assert vn["hq_margin_pct"] is None
    assert vn["transfer_total"] == sg["transfer_total"]
    for line in vn["lines"]:
        assert line["customer_unit_price"] is None
        assert line["customer_amount"] is None
        assert line["hq_margin"] is None
        assert line["margin_pct"] is None
        assert line["transfer_unit_price"] is not None


def test_unmapped_transfer_price_blocks_conversion_until_mapped_inline():
    seeded = client.post("/api/erp-bridge/seed/unmapped?role=sg")
    assert seeded.status_code == 201
    order = seeded.json()["order"]
    order_id = order["order_id"]

    assert order["status"] == "needs_attention"
    assert order["can_convert"] is False
    assert order["can_export"] is False
    assert "KD-LC-7105" in order["unmapped_skus"]

    # Conversion and exports must be blocked while unmapped
    assert client.post(f"/api/erp-bridge/orders/{order_id}/convert").status_code == 409
    assert client.get(f"/api/erp-bridge/orders/{order_id}/export.csv?target=dual").status_code == 409
    assert client.get(f"/api/erp-bridge/orders/{order_id}/export.pdf?target=vn").status_code == 409

    # Map the missing transfer price inline
    mapped = client.put(
        "/api/erp-bridge/transfer-prices/KD-LC-7105",
        json={"transfer_price": 355.0, "vn_item_code": "VN-BOM-LC7105", "lead_time_days": 30, "updated_by": "Wesley"},
    )
    assert mapped.status_code == 200
    assert mapped.json()["mapping"]["transfer_price"] == 355.0

    # Order is now ready, convertible, and exportable
    refreshed = client.get(f"/api/erp-bridge/orders/{order_id}?role=sg").json()
    assert refreshed["status"] == "ready"
    assert refreshed["can_convert"] is True
    assert refreshed["can_export"] is True
    assert refreshed["unmapped_count"] == 0

    conv = client.post(f"/api/erp-bridge/orders/{order_id}/convert", json={"converted_by": "Wesley"})
    assert conv.status_code == 200
    assert conv.json()["converted"] is True


def test_rush_order_lead_time_advisor_and_hybrid_ai_fallback(monkeypatch):
    clean = client.post("/api/erp-bridge/seed/clean?role=sg").json()["order"]
    assert clean["lead_time_risk"]["risk_level"] == "feasible"
    assert clean["lead_time_risk"]["ai_used"] is False
    assert clean["lead_time_risk"]["tokens"] == 0

    rush = client.post("/api/erp-bridge/seed/rush?role=sg").json()["order"]
    assert rush["lead_time_risk"]["risk_level"] == "rush"
    assert rush["lead_time_risk"]["available_days"] < rush["lead_time_risk"]["required_days"]
    assert rush["lead_time_risk"]["shipping_buffer_days"] == 12  # >300 units adds 5d buffer
    assert any(i["code"] == "rush_order_risk" for i in rush["issues"])

    # Mock OpenAI enabled -> hybrid advisor runs and tracks tokens
    monkeypatch.setattr(llm, "api_key", lambda: "test-key")
    monkeypatch.setattr(
        bridge_service,
        "_ai_advisor_summary",
        lambda order, lines, base: {
            "summary": "Split Binh Duong Plant 1 & 2 shifts and negotiate a 14-day ETD extension.",
            "recommendations": ["Prioritize KD-SB-4402 teak curing.", "Air-sample first 40 chairs if urgent."],
            "tokens": 184,
        },
    )
    ai_res = client.post(f"/api/erp-bridge/orders/{rush['order_id']}/advisor", json={"role": "vn"})
    assert ai_res.status_code == 200
    ai_body = ai_res.json()
    assert ai_body["confidentiality_masked"] is True
    assert ai_body["lead_time_risk"]["ai_used"] is True
    assert ai_body["lead_time_risk"]["tokens"] == 184
    assert ai_body["lead_time_risk"]["method"] == "hybrid"

    # Graceful fallback when LLM call returns None / fails
    monkeypatch.setattr(bridge_service, "_ai_advisor_summary", lambda order, lines, base: None)
    fallback_res = client.post(f"/api/erp-bridge/orders/{rush['order_id']}/advisor", json={"role": "sg"}).json()
    assert fallback_res["lead_time_risk"]["ai_used"] is False
    assert fallback_res["lead_time_risk"]["method"] == "rules"


def test_navision_2013_csv_and_pdf_exports_enforce_price_masking():
    order_id = _intake_submit_and_approve("clean")

    # VN CSV must never expose customer contract prices (e.g. 145.00, 1280.00) or customer price columns
    vn_csv = client.get(f"/api/erp-bridge/orders/{order_id}/export.csv?target=vn")
    assert vn_csv.status_code == 200
    assert vn_csv.headers["content-type"].startswith("text/csv")
    assert "KODA_VN_FACTORY" in vn_csv.text
    assert "VN-BOM-CH2047" in vn_csv.text
    assert "96.00" in vn_csv.text
    assert "customer_unit_price" not in vn_csv.text
    assert "1280.00" not in vn_csv.text

    # SG CSV contains customer contract prices and HQ margin
    sg_csv = client.get(f"/api/erp-bridge/orders/{order_id}/export.csv?target=sg")
    assert sg_csv.status_code == 200
    assert "KODA_SG_HQ" in sg_csv.text
    assert "1280.00" in sg_csv.text
    assert "CUSTOMER_CONTRACT" in sg_csv.text

    # Dual CSV contains both entities, with VN lines masked
    dual_csv = client.get(f"/api/erp-bridge/orders/{order_id}/export.csv?target=dual")
    assert dual_csv.status_code == 200
    assert "KODA_SG_HQ" in dual_csv.text
    assert "KODA_VN_FACTORY" in dual_csv.text
    assert "MASKED" in dual_csv.text

    # Dual PDF renders 2 pages; VN PDF renders 1 masked page without contract total
    dual_pdf = client.get(f"/api/erp-bridge/orders/{order_id}/export.pdf?target=dual")
    assert dual_pdf.status_code == 200
    assert dual_pdf.content.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(dual_pdf.content))
    assert len(reader.pages) == 2

    vn_pdf = client.get(f"/api/erp-bridge/orders/{order_id}/export.pdf?target=vn")
    assert vn_pdf.status_code == 200
    vn_reader = PdfReader(io.BytesIO(vn_pdf.content))
    assert len(vn_reader.pages) == 1
    vn_text = vn_reader.pages[0].extract_text() or ""
    assert "CONFIDENTIALITY BOUNDARY" in vn_text
    assert "VN-BOM-CH2047" in vn_text
    assert "1280.00" not in vn_text


def test_error_states_for_missing_unapproved_and_invalid_inputs():
    # Missing order -> 404
    assert client.get("/api/erp-bridge/orders/nonexistent").status_code == 404
    assert client.post("/api/erp-bridge/orders/nonexistent/convert").status_code == 404
    assert client.post("/api/erp-bridge/seed/unknown-scenario").status_code == 404

    # Pending (unapproved) order -> 409 on convert and export
    pending_id = store.orders["orders"][1]["id"]  # ord-2 starts as 'extracted'
    assert client.post(f"/api/erp-bridge/orders/{pending_id}/convert").status_code == 409
    assert client.get(f"/api/erp-bridge/orders/{pending_id}/export.csv?target=dual").status_code == 409
    assert client.get(f"/api/erp-bridge/orders/{pending_id}/export.pdf?target=dual").status_code == 409

    # Invalid role / target / negative transfer price -> 422
    assert client.get("/api/erp-bridge/orders?role=hacker").status_code == 422
    assert client.get(f"/api/erp-bridge/orders/{pending_id}/export.csv?target=all").status_code == 422
    assert client.put("/api/erp-bridge/transfer-prices/KD-LC-7105", json={"transfer_price": -10}).status_code == 422
