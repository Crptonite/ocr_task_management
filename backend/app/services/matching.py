"""2-way matching: invoice vs purchase order.

Owner: Aeric (backend). Rules are placeholders until Koda confirms tolerances.
"""

PRICE_TOLERANCE = 0.01  # 1% unit price drift allowed
TAX_TOLERANCE = 0.50    # currency units allowed for rounding


def match_invoice(invoice: dict, po: dict | None, seen_numbers: set[str] | None = None) -> dict:
    flags: list[dict] = []

    if seen_numbers and invoice["invoice_number"] in seen_numbers:
        flags.append({"level": "error", "message": "Possible duplicate invoice number"})

    if po is None:
        flags.append({"level": "error", "message": f"No purchase order found for {invoice.get('po_number')}"})
        return {"status": "mismatch", "flags": flags}

    if invoice["supplier"] != po["supplier"]:
        flags.append({"level": "error", "message": "Supplier does not match PO"})

    po_lines = {line["sku"]: line for line in po["lines"]}
    subtotal = 0.0
    for line in invoice["lines"]:
        subtotal += line["qty"] * line["unit_price"]
        po_line = po_lines.get(line["sku"])
        if po_line is None:
            flags.append({"level": "error", "message": f"{line['sku']}: not on PO"})
            continue
        if line["qty"] > po_line["qty"]:
            flags.append({"level": "error", "message": f"{line['sku']}: billed {line['qty']}, PO only {po_line['qty']}"})
        drift = (line["unit_price"] - po_line["unit_price"]) / po_line["unit_price"]
        if abs(drift) > PRICE_TOLERANCE:
            flags.append({"level": "warning", "message": f"{line['sku']}: unit price {drift:+.1%} vs PO"})

    expected_tax = round(subtotal * invoice.get("tax_rate", 0), 2)
    if abs(expected_tax - invoice.get("tax_amount", 0)) > TAX_TOLERANCE:
        flags.append({"level": "error", "message": f"Tax should be {expected_tax:.2f}, invoice shows {invoice.get('tax_amount', 0):.2f}"})

    if any(f["level"] == "error" for f in flags):
        status = "mismatch"
    elif flags:
        status = "review"
    else:
        status = "matched"

    return {"status": status, "flags": flags, "subtotal": round(subtotal, 2), "expected_tax": expected_tax}

