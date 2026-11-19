"""Tests for Qizhi's 6b (Part 2) 3-way match, discrepancy tasks, approval workflow and audit trail."""
import copy
import io
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from PIL import Image

from app import database, store as app_store
from app.ai import llm
from app.main import app
from app.services import documents, supabase_store
from qizhi import service
from qizhi.matching import match_invoice, parse_date
from qizhi.receipt_parser import parse_amount, parse_receipt_text
from qizhi.sample_data import PO_1001, RECEIPT_TEXT, SCENARIOS
from qizhi.store import USERS, Store, StoreError
from qizhi.suggester import suggest_tasks

client = TestClient(app)
API = "/api/three-way-match"
TODAY = date(2026, 11, 19)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Never touch live APIs, databases or repo CSVs, and start every test with an empty task store."""
    monkeypatch.setattr(llm, "api_key", lambda: None)
    monkeypatch.setattr(supabase_store, "enabled", lambda: False)
    monkeypatch.setattr(documents, "CSV_PATH", tmp_path / "documents.csv")
    monkeypatch.setenv("DATABASE_URL", "off")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    database.close()
    app_store.reset()
    service.store.reset()
    yield
    app_store.reset()
    database.close()


def user(uid):
    return {**USERS[uid], "id": uid}


def run(name, today=TODAY):
    sc = SCENARIOS[name]
    receipt = parse_receipt_text(sc["receipt_text"]) if sc["receipt_text"] else None
    return match_invoice(sc["invoice"], PO_1001 if sc["invoice"]["po_number"] else None, receipt, today=today)


def kinds(result):
    return [d["type"] for d in result["discrepancies"]]


def invoice(**over):
    inv = copy.deepcopy(SCENARIOS["clean"]["invoice"])
    inv.update(over)
    return inv


# ---------------------------------------------------------------- receipt parsing
def test_receipt_amounts_handle_decimal_commas_and_ocr_spaces():
    assert parse_amount("$158,44") == Decimal("158.44")
    assert parse_amount("1,234.56") == Decimal("1234.56")
    assert parse_amount("$158 ,44") == Decimal("158.44")


def test_receipt_wrapped_lines_and_unit_price_derivation():
    r = parse_receipt_text(RECEIPT_TEXT)
    assert [(i["qty"], i["line_total"]) for i in r["items"]] == [
        (3, Decimal("158.44")), (3, Decimal("46.11")), (1, Decimal("79.31"))]
    assert r["items"][1]["description"] == "Portable USB Power Adapter"
    assert r["items"][1]["unit_price_2dp"] == Decimal("15.37")
    assert r["ocr_trusted"] and r["total"] == Decimal("307.99")
    assert any("differs from transaction date" in w for w in r["warnings"])


def test_receipt_with_zero_quantity_is_skipped_not_a_crash():
    r = parse_receipt_text("a\n-----------\ncashier x\n0 Widget   $5,00\nSUBTOTAL $0,00\n")
    assert r["items"] == [] and any("quantity 0" in w for w in r["warnings"])


# ---------------------------------------------------------------- matching rules
def test_clean_invoice_matches_receipt_despite_rounding():
    assert [k for k in kinds(run("clean")) if k in ("PRICE_MISMATCH", "QTY_MISMATCH")] == []


def test_price_qty_and_extra_line_are_flagged_against_po_and_receipt():
    found = {(d["type"], d["source"]) for d in run("price_qty")["discrepancies"]}
    assert {("PRICE_MISMATCH", "po"), ("PRICE_MISMATCH", "receipt"), ("QTY_MISMATCH", "po"),
            ("QTY_MISMATCH", "receipt"), ("LINE_NOT_ON_PO", "po")} <= found


def test_missing_po_blocks_and_needs_approval():
    r = run("missing_po")
    assert r["status"] == "BLOCKED" and "MISSING_PO" in kinds(r)
    assert next(s for s in suggest_tasks(r) if s["type"] == "MISSING_PO")["requires_approval"]


def test_unknown_po_number_is_flagged():
    assert "PO_NOT_FOUND" in kinds(match_invoice(invoice(po_number="PO-9999"), None, None, today=TODAY))


def test_dates_parse_day_first_and_reject_garbage():
    assert parse_date("2026-11-05") == date(2026, 11, 5)
    assert parse_date("05/11/2026") == date(2026, 11, 5)
    assert parse_date("30 September 2025") == date(2025, 9, 30)
    assert parse_date("not a date") is None


@pytest.mark.parametrize("over,po_over,expected", [
    ({"date": "2026-11-05"}, {}, "INVOICE_BEFORE_PO"),
    ({"date": "2026-11-18"}, {"po_date": "2026-01-01", "valid_until": None}, "INVOICE_LATE"),
    ({"date": "2026-11-18"}, {"valid_until": "2026-11-15"}, "PO_EXPIRED"),
    ({"date": "2026-12-25"}, {}, "INVOICE_DATE_FUTURE"),
    ({"date": "garbage"}, {}, "INVOICE_DATE_MISSING"),
])
def test_date_rules(over, po_over, expected):
    assert expected in kinds(match_invoice(invoice(**over), dict(PO_1001, **po_over), None, today=TODAY))


def test_same_day_invoice_is_ok():
    assert "INVOICE_BEFORE_PO" not in kinds(match_invoice(invoice(date="2026-11-10"), PO_1001, None, today=TODAY))


def test_total_over_po_is_flagged_with_variance():
    r = match_invoice(SCENARIOS["dates_total"]["invoice"], PO_1001, None, today=TODAY)
    assert next(d for d in r["discrepancies"] if d["type"] == "PO_TOTAL_MISMATCH")["variance"] == "20.00"


def test_partial_billing_is_not_double_flagged():
    inv = invoice(subtotal="204.54", tax="17.38", total="221.92")
    inv["lines"] = inv["lines"][:2]
    r = match_invoice(inv, PO_1001, None, today=TODAY)
    assert "ORDERED_NOT_BILLED" in kinds(r) and "PO_TOTAL_MISMATCH" not in kinds(r)


# ---------------------------------------------------------------- tasks, approval, audit (store)
@pytest.fixture
def task():
    st = Store()
    suggestion = next(s for s in suggest_tasks(run("missing_po")) if s["type"] == "MISSING_PO")
    t, _ = st.create_task(user("alex"), "INV-5003", suggestion)
    return st, t, suggestion


def test_task_creation_is_idempotent(task):
    st, _, suggestion = task
    assert st.create_task(user("alex"), "INV-5003", suggestion)[1] is False


def test_cannot_resolve_a_task_that_needs_approval(task):
    st, t, _ = task
    with pytest.raises(StoreError):
        st.update_task(user("alex"), t["id"], status="resolved")


def test_only_the_owning_department_head_can_decide(task):
    st, t, _ = task
    st.request_approval(user("alex"), t["id"], "Raise retrospective PO")
    for who, decision, comment in [("sam", "approved", ""), ("fiona", "approved", ""), ("priya", "rejected", "")]:
        with pytest.raises(StoreError):
            st.decide(user(who), t["id"], decision, comment)
    st.decide(user("priya"), t["id"], "approved", "OK, PO raised")
    assert st.tasks[t["id"]]["status"] == "resolved"


def test_head_cannot_approve_their_own_request(task):
    st, t, _ = task
    st.request_approval(user("priya"), t["id"], "Self serve")
    with pytest.raises(StoreError) as err:
        st.decide(user("priya"), t["id"], "approved", "")
    assert err.value.code == 403


def test_audit_chain_detects_tampering(task):
    st, t, _ = task
    st.request_approval(user("alex"), t["id"], "x y z")
    assert st.verify_audit()["valid"]
    st.audit_log[0]["details"]["priority"] = "P4"
    verdict = st.verify_audit()
    assert not verdict["valid"] and verdict["broken_at_seq"] == 1


# ---------------------------------------------------------------- API
def match_payload(name="price_qty", **over):
    sc = SCENARIOS[name]
    return {"invoice": sc["invoice"], "receipt_text": sc["receipt_text"], **over}


def test_match_endpoint_creates_tasks_and_audit_events():
    res = client.post(f"{API}/match", json=match_payload())
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "REVIEW" and body["tasks"] and body["receipt_used"]
    tasks = client.get(f"{API}/tasks").json()["tasks"]
    assert len(tasks) == len(body["tasks"])
    assert client.get(f"{API}/audit", params={"invoice_no": "INV-5002"}).json()
    assert client.get(f"{API}/audit/verify").json()["valid"]
    assert client.get(f"{API}/matches/INV-5002").json()["status"] == "REVIEW"


def test_rerunning_a_match_does_not_duplicate_tasks():
    client.post(f"{API}/match", json=match_payload())
    first = len(client.get(f"{API}/tasks").json()["tasks"])
    client.post(f"{API}/match", json=match_payload())
    assert len(client.get(f"{API}/tasks").json()["tasks"]) == first


def test_clean_invoice_has_no_blocking_state_without_receipt():
    res = client.post(f"{API}/match", json=match_payload("clean", receipt_text=None))
    assert res.status_code == 200 and not res.json()["receipt_used"]


def test_unknown_match_result_is_404():
    assert client.get(f"{API}/matches/NOPE").status_code == 404


@pytest.mark.parametrize("patch", [
    {"lines": []},
    {"invoice_no": ""},
    {"lines": [{"description": "x", "qty": -1, "unit_price": 1}]},
    {"lines": [{"description": "x", "qty": 1, "unit_price": -5}]},
])
def test_invalid_invoice_is_rejected_by_validation(patch):
    payload = match_payload("clean")
    payload["invoice"] = {**payload["invoice"], **patch}
    assert client.post(f"{API}/match", json=payload).status_code == 422


def test_oversized_receipt_text_is_rejected():
    assert client.post(f"{API}/match", json=match_payload(receipt_text="x" * 20_001)).status_code == 422


def test_unknown_user_is_unauthorised():
    res = client.post(f"{API}/match", json=match_payload(), headers={"X-User": "mallory"})
    assert res.status_code == 401


def test_approval_flow_and_segregation_of_duties_over_http():
    client.post(f"{API}/match", json=match_payload("missing_po"))
    task_id = next(t["id"] for t in client.get(f"{API}/tasks").json()["tasks"] if t["type"] == "MISSING_PO")
    path = f"{API}/tasks/{task_id}"
    assert client.patch(path, json={"status": "resolved"}).status_code == 409           # needs approval first
    assert client.patch(path, json={"status": "awaiting_approval"}).status_code == 422  # cannot skip the workflow
    assert client.post(f"{path}/request-approval", json={"proposed_resolution": "Raise a retrospective PO"}).status_code == 200
    as_head = {"X-User": "priya"}
    assert client.post(f"{path}/decision", json={"decision": "approved"}, headers={"X-User": "alex"}).status_code == 403
    assert client.post(f"{path}/decision", json={"decision": "rejected"}, headers=as_head).status_code == 400
    done = client.post(f"{path}/decision", json={"decision": "approved", "comment": "OK"}, headers=as_head)
    assert done.status_code == 200 and done.json()["status"] == "resolved"
    assert [e["action"] for e in client.get(f"{API}/audit", params={"task_id": task_id}).json()][-2:] == [
        "APPROVAL_REQUESTED", "APPROVED"]


def test_unknown_task_is_404():
    assert client.patch(f"{API}/tasks/T-9999", json={"status": "open"}).status_code == 404


def test_scenarios_and_users_are_listed():
    assert {s["id"] for s in client.get(f"{API}/scenarios").json()} == set(SCENARIOS)
    assert {u["id"] for u in client.get(f"{API}/users").json()} == set(USERS)


# ---------------------------------------------------------------- receipt upload
def text_pdf(text):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in text.splitlines():
        pdf.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def upload(data, name="receipt.pdf"):
    return client.post(f"{API}/receipts/extract", files={"file": (name, data, "application/octet-stream")})


def test_text_pdf_receipt_is_extracted_and_parsed():
    res = upload(text_pdf(RECEIPT_TEXT))
    assert res.status_code == 200
    body = res.json()
    assert body["method"] == "pdf-text" and len(body["parsed"]["items"]) == 3


def test_wrong_file_type_is_rejected_even_with_a_pdf_name():
    assert upload(b"MZ not a pdf at all", "receipt.pdf").status_code == 415


def test_empty_file_is_rejected():
    assert upload(b"").status_code == 400


def test_oversized_file_is_rejected():
    assert upload(b"%PDF" + b"0" * (10 * 1024 * 1024)).status_code == 413


def test_corrupted_pdf_gives_a_clear_error():
    res = upload(b"%PDF-1.4 this is not really a pdf")
    assert res.status_code == 422 and res.json()["detail"]


def test_photo_without_working_ocr_fails_cleanly(monkeypatch):
    import qizhi.pdf_extract as extract

    def no_ocr(_img):
        raise extract.ExtractError("OCR is not installed on this server.")

    monkeypatch.setattr(extract, "_ocr_image", no_ocr)
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    res = upload(buf.getvalue(), "receipt.png")
    assert res.status_code == 422 and "OCR" in res.json()["detail"]


# ---------------------------------------------------------------- integration with the rest of the app
def test_routes_are_namespaced_and_do_not_shadow_existing_ones():
    paths = set(app.openapi()["paths"])
    assert any(p.startswith(API) for p in paths)
    assert not {"/api/tasks", "/api/me", "/api/users", "/api/audit"} & paths
    assert "/api/invoices" in paths


def test_po_lookup_uses_the_live_register_and_invoices_map_across():
    live = app_store.erp["purchase_orders"][0]
    found = service.find_po(live["po_number"])
    assert found["vendor"] == live["supplier"] and found["lines"] == live["lines"]
    assert service.find_po("PO-NOPE") is None and service.find_po("") is None
    mapped = client.get(f"{API}/invoices").json()
    assert mapped and {"invoice_no", "vendor", "po_number", "lines"} <= set(mapped[0])


def test_review_queue_invoice_can_be_matched_end_to_end():
    inv = client.get(f"{API}/invoices").json()[0]
    res = client.post(f"{API}/match", json={"invoice": inv})
    assert res.status_code == 200 and res.json()["po_found"]


def test_review_queue_mismatches_flag_tax_price_qty_and_create_tasks():
    by_no = {i["invoice_no"]: i for i in client.get(f"{API}/invoices").json()}
    tax_res = client.post(f"{API}/match", json={"invoice": by_no["TFF-5108"]})
    assert tax_res.status_code == 200
    assert "TAX_MISMATCH" in [d["type"] for d in tax_res.json()["discrepancies"]]
    assert tax_res.json()["tasks"]

    pq_res = client.post(f"{API}/match", json={"invoice": by_no["DTW-7742"]})
    assert pq_res.status_code == 200
    pq_types = {d["type"] for d in pq_res.json()["discrepancies"]}
    assert {"PRICE_MISMATCH", "QTY_MISMATCH", "PO_TOTAL_MISMATCH"} <= pq_types
    assert pq_res.json()["tasks"]


def test_full_pipeline_from_aeric_po_intake_through_wesley_lucas_and_qizhi():
    from aeric.service import SAMPLES

    parsed = client.post("/api/po-intake", data={"text": SAMPLES["clean"]["text"]})
    assert parsed.status_code == 200
    sub = client.post("/api/po-intake/submit", json={**parsed.json()["po"], "created_by": "Aeric"})
    assert sub.status_code == 201
    order_id = sub.json()["order"]["id"]

    app_res = client.post(f"/api/orders/{order_id}/approve", json={"approved_by": "Aeric"})
    assert app_res.status_code == 200
    assert client.get(f"/api/erp-bridge/orders/{order_id}").status_code == 200
    assert client.post(f"/api/erp-bridge/orders/{order_id}/convert", json={"converted_by": "Wesley"}).status_code == 200

    gen_res = client.post(f"/api/invoice-queue/{order_id}/generate", json={"generated_by": "Lucas"})
    assert gen_res.status_code == 200
    inv_no = gen_res.json()["invoice"]["invoice_number"]

    mapped = {i["invoice_no"]: i for i in client.get(f"{API}/invoices").json()}
    assert inv_no in mapped
    match_res = client.post(f"{API}/match", json={"invoice": mapped[inv_no]})
    assert match_res.status_code == 200
    body = match_res.json()
    assert body["po_found"] and body["status"] == "MATCHED" and body["discrepancies"] == []


def test_frontend_script_is_served():
    res = client.get("/qizhi/three_way_match.js")
    assert res.status_code == 200 and "3-Way Match" in res.text
