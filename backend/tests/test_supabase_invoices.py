"""Invoice PDFs and rows are saved to Supabase and the file can be opened; outages never lose an upload."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.services import supabase_store as sb
from app.services.invoice_pdf import invoice_from_po, render_invoice_pdf

client = TestClient(app, follow_redirects=False)


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


@pytest.fixture
def pdf():
    po = store.erp["purchase_orders"][0]
    inv = invoice_from_po(po, "clean")
    inv["invoice_number"] = "SB-001"
    return render_invoice_pdf(inv)


@pytest.fixture
def fake_supabase(monkeypatch):
    calls = {"rows": [], "deleted": []}
    monkeypatch.setattr(sb, "enabled", lambda: True)
    monkeypatch.setattr(sb, "upload_file", lambda name, content: f"invoices/abc-{name}")
    monkeypatch.setattr(sb, "save_invoice", lambda inv, path: calls["rows"].append((inv["invoice_number"], path)))
    monkeypatch.setattr(sb, "signed_url", lambda path: f"https://example.supabase.co/sign/{path}?token=t")
    monkeypatch.setattr(sb, "delete_invoice", lambda number, path: calls["deleted"].append((number, path)))
    return calls


def upload(pdf):
    return client.post("/api/invoices/upload", files={"file": ("sb.pdf", pdf, "application/pdf")}).json()


def test_upload_saves_file_and_row(fake_supabase, pdf):
    res = upload(pdf)
    assert res["saved"] is True and res["invoice"]["file_path"] == "invoices/abc-sb.pdf"
    assert fake_supabase["rows"] == [(res["invoice"]["invoice_number"], "invoices/abc-sb.pdf")]


def test_open_file_redirects_to_signed_url(fake_supabase, pdf):
    number = upload(pdf)["invoice"]["invoice_number"]
    res = client.get(f"/api/invoices/{number}/file")
    assert res.status_code == 307 and res.headers["location"].startswith("https://example.supabase.co/sign/invoices/")


def test_supabase_outage_still_queues_invoice(fake_supabase, monkeypatch, pdf):
    def boom(*a):
        raise RuntimeError("Supabase 500")
    monkeypatch.setattr(sb, "upload_file", boom)
    res = upload(pdf)
    assert res["saved"] is False and "Supabase 500" in res["storage_error"] and res["invoice"] is not None


def test_no_file_for_sample_invoice():
    number = store.erp["invoices"][0]["invoice_number"]
    assert client.get(f"/api/invoices/{number}/file").status_code == 404


def test_upload_without_supabase_configured(pdf):
    res = upload(pdf)
    assert res["saved"] is False and res["storage_error"] is None and res["invoice"] is not None


def test_delete_removes_row_and_file(fake_supabase, pdf):
    number = upload(pdf)["invoice"]["invoice_number"]
    assert client.delete(f"/api/invoices/{number}").status_code == 204
    assert fake_supabase["deleted"] == [(number, "invoices/abc-sb.pdf")]


def test_failed_row_insert_removes_uploaded_file(fake_supabase, monkeypatch, pdf):
    removed = []
    monkeypatch.setattr(sb, "save_invoice", lambda *a: (_ for _ in ()).throw(RuntimeError("no table")))
    monkeypatch.setattr(sb, "delete_file", removed.append)
    res = upload(pdf)
    assert res["saved"] is False and removed == ["invoices/abc-sb.pdf"]
    assert "file_path" not in res["invoice"]
