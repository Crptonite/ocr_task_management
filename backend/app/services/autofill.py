"""Fill the header fields an upload could not read, so receipts and scans still reach the queue.

Owner: Aeric (backend). Only header fields are generated; line items are never invented.
Every generated value is listed in invoice["auto_filled"] and flagged for review by matching.
"""
import os
from datetime import date

from app import store

AUTO_INVOICE_PREFIX = "INV-AUTO-"
AUTO_PO_PREFIX = "PO-AUTO-"
UNKNOWN_SUPPLIER = "Unknown supplier"
DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "SGD")


def _next_number(prefix: str, taken: set[str]) -> str:
    stamp = date.today().strftime("%Y%m%d")
    n = 1
    while f"{prefix}{stamp}-{n:03d}" in taken:
        n += 1
    return f"{prefix}{stamp}-{n:03d}"


def fill_missing(draft: dict) -> list[str]:
    """Fill missing header fields on the draft in place; returns the field names that were generated."""
    filled = []
    if not draft.get("invoice_number"):
        draft["invoice_number"] = _next_number(AUTO_INVOICE_PREFIX, {i["invoice_number"] for i in store.erp["invoices"]})
        filled.append("invoice_number")
    if not draft.get("supplier"):
        draft["supplier"] = UNKNOWN_SUPPLIER
        filled.append("supplier")
    if not draft.get("currency"):
        draft["currency"] = DEFAULT_CURRENCY
        filled.append("currency")
    if not draft.get("invoice_date"):
        draft["invoice_date"] = date.today().isoformat()
        filled.append("invoice_date")
    if not draft.get("po_number") and draft.get("lines"):
        draft["po_number"] = _next_number(AUTO_PO_PREFIX, {p["po_number"] for p in store.erp["purchase_orders"]})
        filled.append("po_number")
    return filled


def create_po(invoice: dict) -> dict | None:
    """Add a purchase order built from the invoice lines, for an auto-generated PO number."""
    number = invoice.get("po_number") or ""
    if not number.startswith(AUTO_PO_PREFIX):
        return None
    existing = next((p for p in store.erp["purchase_orders"] if p["po_number"] == number), None)
    if existing:
        return existing
    po = {
        "po_number": number,
        "supplier": invoice["supplier"],
        "currency": invoice.get("currency"),
        "auto_created": True,
        "source_invoice": invoice["invoice_number"],
        "lines": [
            {"sku": line.get("sku") or f"AUTO-{n}", "description": line.get("description") or f"Item {n}",
             "qty": line["qty"], "unit_price": line["unit_price"]}
            for n, line in enumerate(invoice.get("lines") or [], 1)
        ],
    }
    store.erp["purchase_orders"].append(po)
    return po


def restore(invoices: list[dict]) -> None:
    """After loading saved invoices: mark generated values again and rebuild their auto-created POs."""
    for inv in invoices:
        if "auto_filled" not in inv:
            inv["auto_filled"] = [
                field for field, generated in (
                    ("invoice_number", (inv.get("invoice_number") or "").startswith(AUTO_INVOICE_PREFIX)),
                    ("supplier", inv.get("supplier") == UNKNOWN_SUPPLIER),
                    ("po_number", (inv.get("po_number") or "").startswith(AUTO_PO_PREFIX)),
                ) if generated
            ]
        create_po(inv)


def remove_po_for(invoice: dict) -> None:
    """Drop the PO that was auto-created for this invoice."""
    store.erp["purchase_orders"][:] = [
        p for p in store.erp["purchase_orders"]
        if not (p.get("auto_created") and p.get("source_invoice") == invoice["invoice_number"])
    ]
