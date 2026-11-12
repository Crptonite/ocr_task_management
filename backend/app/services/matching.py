"""2-way matching: invoice vs purchase order.

Owner: Aeric (backend). Rules are placeholders until Koda confirms tolerances.
"""
import re

PRICE_TOLERANCE = 0.01  # 1% unit price drift allowed
TAX_TOLERANCE = 0.50    # currency units allowed for rounding

# Reference printed on Spectra sales invoices from the Orders tab, e.g. "Order QA123 / TXN-00005".
SPECTRA_REF = re.compile(r"^\s*Order\s+(\S+)\s*/\s*(TXN-\d+)\s*$", re.IGNORECASE)


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def _missing_po_message(ref: str | None) -> str:
    if not ref:
        return "No PO reference on the invoice"
    spectra = SPECTRA_REF.match(ref)
    if spectra:
        order, txn = spectra.groups()
        return (f"{ref} is a Spectra sales invoice (order {order}, {txn}), not a supplier invoice against a Koda PO. "
                "Review it in the Orders tab invoice queue instead.")
    return f"No purchase order found for {ref}"


def _line_label(n: int, line: dict) -> str:
    return line.get("sku") or f"Line {n} ({line.get('description') or 'no description'})"


def match_invoice(invoice: dict, po: dict | None, seen_numbers: set[str] | None = None) -> dict:
    flags: list[dict] = []
    lines = invoice.get("lines") or []
    subtotal = round(sum(line["qty"] * line["unit_price"] for line in lines), 2)

    if seen_numbers and invoice["invoice_number"] in seen_numbers:
        flags.append({"level": "error", "message": "Possible duplicate invoice number"})

    filled = invoice.get("auto_filled") or []
    if filled:
        names = ", ".join(f.replace("_", " ") for f in filled)
        flags.append({"level": "warning", "message": f"Not readable on the document, auto-filled: {names}. Check before approving."})

    if po is None:
        flags.append({"level": "error", "message": _missing_po_message(invoice.get("po_number"))})
        return {"status": "mismatch", "flags": flags, "subtotal": subtotal}

    if po.get("auto_created"):
        flags.append({"level": "warning", "message": f"{po['po_number']} was auto-created from this invoice. Confirm it with purchasing."})

    if invoice["supplier"] != po["supplier"]:
        flags.append({"level": "error", "message": "Supplier does not match PO"})

    by_sku = {line["sku"]: line for line in po["lines"] if line.get("sku")}
    by_desc = {_norm(line.get("description")): line for line in po["lines"] if line.get("description")}
    for n, line in enumerate(lines, 1):
        label = _line_label(n, line)
        if line.get("sku"):
            po_line = by_sku.get(line["sku"])
        else:
            # Scans and photos often drop the SKU column: fall back to the PO line's description.
            po_line = by_desc.get(_norm(line.get("description")))
            if po_line is not None:
                flags.append({"level": "warning", "message": f"{label}: no SKU on invoice, matched to {po_line['sku']} by description"})
                label = po_line["sku"]
        if po_line is None:
            reason = "not on PO" if line.get("sku") else "no SKU, and no PO line has this description"
            flags.append({"level": "error", "message": f"{label}: {reason}"})
            continue
        if line["qty"] > po_line["qty"]:
            flags.append({"level": "error", "message": f"{label}: billed {line['qty']}, PO only {po_line['qty']}"})
        drift = (line["unit_price"] - po_line["unit_price"]) / po_line["unit_price"]
        if abs(drift) > PRICE_TOLERANCE:
            flags.append({"level": "warning", "message": f"{label}: unit price {drift:+.1%} vs PO"})

    expected_tax = round(subtotal * invoice.get("tax_rate", 0), 2)
    if abs(expected_tax - invoice.get("tax_amount", 0)) > TAX_TOLERANCE:
        flags.append({"level": "error", "message": f"Tax should be {expected_tax:.2f}, invoice shows {invoice.get('tax_amount', 0):.2f}"})

    if any(f["level"] == "error" for f in flags):
        status = "mismatch"
    elif flags:
        status = "review"
    else:
        status = "matched"

    return {"status": status, "flags": flags, "subtotal": subtotal, "expected_tax": expected_tax}
