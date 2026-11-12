import csv

from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.services import documents

client = TestClient(app)


def rows():
    with open(documents.CSV_PATH, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_documents_list_has_invoices_and_orders():
    store.reset()
    docs = client.get("/api/documents").json()
    assert {"Invoice"} <= {d["Type"] for d in docs}
    assert any(d["Type"].endswith("order") for d in docs)
    assert set(documents.COLUMNS) <= set(docs[0])


def test_csv_updates_when_order_added_and_deleted():
    store.reset()
    documents.sync_csv()
    before = len(rows())
    store.orders["orders"].append({"id": "ord-999", "order_number": "SO-999", "type": "sales", "counterparty": "Acme",
                                   "order_date": "2026-01-01", "currency": "SGD", "total": 10.0, "status": "extracted", "lines": [], "source_file": "x"})
    client.patch("/api/orders/ord-999", json={"counterparty": "Acme Pte"})
    assert len(rows()) == before + 1
    client.delete("/api/orders/ord-999")
    assert len(rows()) == before


def test_csv_endpoint():
    res = client.get("/api/documents.csv")
    assert res.status_code == 200
    assert res.text.startswith("Document,Type,Company,Date,Amount,Status")
