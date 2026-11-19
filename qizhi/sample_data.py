"""Demo data for the 3-way match: one hard-copy receipt (OCR output, note the decimal commas), the demo PO
register and four invoice scenarios covering the clean path and the main error states."""

RECEIPT_TEXT = """Modern POS Receipt
30 September 2025
01:55
----------------------------------------
Nova Enterprises
Tel. (415) 555-8937
info@novaenterprises.com
www.novaenterprises.com
----------------------------------------
Your cashier was Mitchell U.
----------------------------------------
3 Wireless
Noise-Canceling Earbuds   $158,44
3 Portable USB Power
Adapter   $46,11
1 Smart LED Touch Desk
Lamp   $79,31

SUBTOTAL   $283,86
TAX (8,5%)   $24,13

TOTAL   $307,99
Card number   **** **** **** 7085
Card type   Debit
Card entry   Chip
Date/time   11/20/2019 11:09 AM
Reference #   62845289260246240685C
Status   APPROVED
"""

PO_1001 = {"po_number": "PO-1001", "vendor": "Nova Enterprises", "po_date": "2026-11-10",
           "valid_until": "2026-12-31", "lines": [
    {"sku": "NC-EB-01", "description": "Wireless Noise-Canceling Earbuds", "qty": 3, "unit_price": "52.81"},
    {"sku": "USB-PA-02", "description": "Portable USB Power Adapter", "qty": 3, "unit_price": "15.37"},
    {"sku": "LED-DL-03", "description": "Smart LED Touch Desk Lamp", "qty": 1, "unit_price": "79.31"}]}

PO_REGISTER = {"PO-1001": PO_1001}


def _inv(no, po, lines, subtotal, tax, total):
    return {"invoice_no": no, "vendor": "Nova Enterprises", "po_number": po, "date": "2026-11-18",
            "lines": lines, "subtotal": subtotal, "tax": tax, "total": total}


def _line(sku, desc, qty, unit, total):
    return {"sku": sku, "description": desc, "qty": qty, "unit_price": unit, "line_total": total}


EARBUDS = "Wireless Noise-Canceling Earbuds"
ADAPTER = "Portable USB Power Adapter"
LAMP = "Smart LED Touch Desk Lamp"

SCENARIOS = {
    "clean": {
        "label": "Clean match",
        "invoice": _inv("INV-5001", "PO-1001", [
            _line("NC-EB-01", EARBUDS, 3, "52.81", "158.43"),
            _line("USB-PA-02", ADAPTER, 3, "15.37", "46.11"),
            _line("LED-DL-03", LAMP, 1, "79.31", "79.31")],
            "283.85", "24.13", "307.98"),
        "receipt_text": RECEIPT_TEXT},
    "price_qty": {
        "label": "Price and quantity mismatch",
        "invoice": _inv("INV-5002", "PO-1001", [
            _line("NC-EB-01", EARBUDS, 3, "58.99", "176.97"),
            _line("USB-PA-02", ADAPTER, 8, "15.37", "122.96"),
            _line("LED-DL-03", LAMP, 1, "79.31", "79.31"),
            _line("", "Express handling fee", 1, "45.00", "45.00")],
            "424.24", "36.06", "460.30"),
        "receipt_text": RECEIPT_TEXT},
    "missing_po": {
        "label": "Missing PO number",
        "invoice": _inv("INV-5003", "", [
            _line("", EARBUDS, 3, "52.81", "158.43"),
            _line("", ADAPTER, 3, "15.37", "46.11")],
            "204.54", "17.38", "221.92"),
        "receipt_text": RECEIPT_TEXT},
    "dates_total": {
        "label": "Invoice before PO date, total over PO",
        "invoice": {**_inv("INV-5004", "PO-1001", [
            _line("NC-EB-01", EARBUDS, 3, "52.81", "158.43"),
            _line("USB-PA-02", ADAPTER, 3, "15.37", "46.11"),
            _line("LED-DL-03", LAMP, 1, "79.31", "79.31"),
            _line("", "Rush delivery surcharge", 1, "20.00", "20.00")],
            "303.85", "25.83", "329.68"), "date": "2026-11-05"},
        "receipt_text": ""},
}
