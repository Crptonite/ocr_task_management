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



def test_spectra_sales_invoice_gets_a_clear_message():
    inv = make_invoice(po_number="Order QA123 / TXN-00005", lines=[{"sku": None, "description": "SSD", "qty": 1, "unit_price": 165.0}])
    result = match_invoice(inv, None)
    assert result["status"] == "mismatch"
    assert "Spectra sales invoice (order QA123, TXN-00005)" in result["flags"][0]["message"]
    assert result["subtotal"] == 165.0


def test_missing_po_reference():
    assert match_invoice(make_invoice(po_number=None), None)["flags"][0]["message"] == "No PO reference on the invoice"


def test_line_without_sku_matches_po_by_description():
    po = {**PO, "lines": [{"sku": "A", "description": "Birch panel", "qty": 10, "unit_price": 5.0}]}
    inv = make_invoice(lines=[{"sku": None, "description": "birch  PANEL", "qty": 10, "unit_price": 5.0}])
    result = match_invoice(inv, po)
    assert result["status"] == "review"
    assert "matched to A by description" in result["flags"][0]["message"]


def test_line_without_sku_or_known_description_is_an_error():
    inv = make_invoice(lines=[{"sku": None, "description": "Mystery item", "qty": 1, "unit_price": 5.0}])
    result = match_invoice(inv, PO)
    assert result["status"] == "mismatch"
    assert result["flags"][0]["message"] == "Line 1 (Mystery item): no SKU, and no PO line has this description"
