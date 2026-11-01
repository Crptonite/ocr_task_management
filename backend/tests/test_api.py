"""Owner: Wesley (testing)."""
from fastapi.testclient import TestClient

from app import store
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



def test_delete_invoice_then_404():
    store.reset()
    assert client.delete("/api/invoices/HHE-30551").status_code == 204
    assert client.get("/api/invoices/HHE-30551").status_code == 404
    assert client.delete("/api/invoices/HHE-30551").status_code == 404


def test_cannot_delete_po_that_still_has_invoices():
    store.reset()
    res = client.delete("/api/purchase-orders/PO-2026-0412")
    assert res.status_code == 409 and "HHE-30551" in res.json()["detail"]
    client.delete("/api/invoices/HHE-30551")
    assert client.delete("/api/purchase-orders/PO-2026-0412").status_code == 204
    assert all(po["po_number"] != "PO-2026-0412" for po in client.get("/api/purchase-orders").json())
    store.reset()
