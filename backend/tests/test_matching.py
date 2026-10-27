"""Owner: Wesley (testing)."""
from app.services.matching import match_invoice

PO = {
    "po_number": "PO-1",
    "supplier": "Acme",
    "lines": [{"sku": "A", "qty": 10, "unit_price": 5.0}],
}


def make_invoice(**overrides):
    inv = {
        "invoice_number": "INV-1",
        "po_number": "PO-1",
        "supplier": "Acme",
        "tax_rate": 0.0,
        "tax_amount": 0.0,
        "lines": [{"sku": "A", "qty": 10, "unit_price": 5.0}],
    }
    inv.update(overrides)
    return inv


def test_clean_invoice_matches():
    assert match_invoice(make_invoice(), PO)["status"] == "matched"


def test_price_drift_needs_review():
    inv = make_invoice(lines=[{"sku": "A", "qty": 10, "unit_price": 5.5}])
    assert match_invoice(inv, PO)["status"] == "review"


def test_over_billed_qty_is_mismatch():
    inv = make_invoice(lines=[{"sku": "A", "qty": 12, "unit_price": 5.0}])
    assert match_invoice(inv, PO)["status"] == "mismatch"


def test_wrong_tax_is_mismatch():
    inv = make_invoice(tax_rate=0.09, tax_amount=10.0)
    assert match_invoice(inv, PO)["status"] == "mismatch"


def test_missing_po_is_mismatch():
    assert match_invoice(make_invoice(), None)["status"] == "mismatch"

