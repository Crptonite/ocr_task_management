"""Owner: Wesley (testing). Spectra order validation and API."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.services.orders import orders_to_csv, validate_order

client = TestClient(app)
CATALOG = [{"sku": "A-1", "name": "Widget", "unit_price": 10.0}]


def order(**overrides):
    base = {
        "order_number": "SO-1", "counterparty": "Acme", "order_date": "2026-10-01",
        "delivery_date": "2026-10-05", "total": 20.0,
        "lines": [{"sku": "A-1", "description": "Widget", "quantity": 2, "unit_price": 10.0, "amount": 20.0}],
    }
    return {**base, **overrides}


@pytest.fixture(autouse=True)
def fresh_store():
    store.reset()


def test_clean_order_is_ready():
    assert validate_order(order(), CATALOG)["status"] == "ready"


def test_missing_header_fields():
    issues = validate_order(order(order_number=None, delivery_date=None), CATALOG)["issues"]
    assert "Missing order number" in issues
    assert "Missing delivery date" in issues


def test_delivery_before_order_date():
    assert "Delivery date is before order date" in validate_order(order(delivery_date="2026-09-01"), CATALOG)["issues"]


def test_line_checks():
    lines = [
        {"sku": "ZZZ", "description": "?", "quantity": 1, "unit_price": 5.0, "amount": 5.0},
        {"sku": "A-1", "description": "Widget", "quantity": 1, "unit_price": 13.0, "amount": 15.0},
    ]
    result = validate_order(order(lines=lines, total=20.0), CATALOG)
    assert result["line_issues"][0] == ["SKU not in catalogue"]
    assert "Amount ≠ qty × price" in result["line_issues"][1]
    assert any(i.startswith("Price +30%") for i in result["line_issues"][1])
    assert "2 line(s) need attention" in result["issues"]


def test_total_mismatch():
    assert any("≠ line total" in i for i in validate_order(order(total=25.0), CATALOG)["issues"])


def test_csv_has_one_row_per_line():
    rows = orders_to_csv([order(type="sales", currency="SGD")]).strip().split("\r\n")
    assert rows[0].startswith("order_number,type,counterparty")
    assert len(rows) == 2


def test_list_orders_has_validation():
    orders = client.get("/api/orders").json()
    assert {o["validation"]["status"] for o in orders} == {"ready", "needs_attention"}


def test_approve_then_export_flow():
    ready = next(o for o in client.get("/api/orders").json() if o["validation"]["status"] == "ready")
    assert client.post(f"/api/orders/{ready['id']}/approve").json()["status"] == "approved"
    assert client.post(f"/api/orders/{ready['id']}/approve").status_code == 409

    res = client.get("/api/orders/export.csv")
    assert res.headers["content-type"].startswith("text/csv")
    assert ready["order_number"] in res.text
    assert client.get(f"/api/orders/{ready['id']}").json()["status"] == "exported"
    # Already exported, so a second export has only the header.
    assert client.get("/api/orders/export.csv").text.count("\r\n") == 1


def test_cannot_approve_order_with_issues():
    bad = next(o for o in client.get("/api/orders").json() if o["validation"]["status"] == "needs_attention")
    assert client.post(f"/api/orders/{bad['id']}/approve").status_code == 409


def test_unknown_order_404():
    assert client.get("/api/orders/nope").status_code == 404
