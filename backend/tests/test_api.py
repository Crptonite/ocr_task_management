"""Owner: Wesley (testing)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_list_invoices_has_match_result():
    invoices = client.get("/api/invoices").json()
    assert len(invoices) > 0
    assert {"matched", "review", "mismatch"} >= {i["match"]["status"] for i in invoices}


def test_unknown_invoice_404():
    assert client.get("/api/invoices/NOPE").status_code == 404

