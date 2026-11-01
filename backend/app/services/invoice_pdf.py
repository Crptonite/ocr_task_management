"""Generate a supplier invoice PDF from a purchase order.

Owner: Aeric (backend). Used to make realistic test documents for the upload →
extract → match flow. `variant` injects a known problem so each flag can be demoed.
"""
from datetime import date

from fpdf import FPDF

GST_RATE = 0.09  # Singapore suppliers charge GST; overseas suppliers do not

VARIANTS = {
    "clean": "Matches the PO exactly",
    "price": "First line billed 5% above PO price",
    "qty": "First line billed 10% more units than ordered",
    "tax": "GST amount wrong",
}


def invoice_from_po(po: dict, variant: str = "clean", invoice_date: date | None = None) -> dict:
    """Build the invoice data a supplier would send for this PO."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant!r}")
    lines = [dict(line) for line in po["lines"]]
    if variant == "price":
        lines[0]["unit_price"] = round(lines[0]["unit_price"] * 1.05, 2)
    if variant == "qty":
        lines[0]["qty"] = round(lines[0]["qty"] * 1.1)
    for line in lines:
        line["amount"] = round(line["qty"] * line["unit_price"], 2)

    subtotal = round(sum(line["amount"] for line in lines), 2)
    tax_rate = GST_RATE if po["currency"] == "SGD" else 0.0
    tax_amount = round(subtotal * tax_rate, 2)
    if variant == "tax":
        tax_rate = tax_rate or GST_RATE
        tax_amount = round(subtotal * tax_rate * 0.5, 2)  # supplier halved the GST

    # Same PO + variant always gives the same number, so re-uploading triggers the duplicate check.
    suffix = po["po_number"].split("-")[-1]
    return {
        "invoice_number": f"INV-{suffix}-{variant.upper()}",
        "po_number": po["po_number"],
        "supplier": po["supplier"],
        "invoice_date": (invoice_date or date.today()).isoformat(),
        "currency": po["currency"],
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "lines": lines,
        "subtotal": subtotal,
        "total": round(subtotal + tax_amount, 2),
    }


def render_invoice_pdf(inv: dict) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=20)
    pdf.add_page()
    pdf.set_margins(18, 18, 18)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, inv["supplier"], new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(110)
    pdf.cell(0, 5, "Supplier to Koda Ltd - furniture components", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # Keep "Label: value" on one line each; the extractor reads them back with regexes.
    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Invoice No", inv["invoice_number"]),
        ("Invoice Date", inv["invoice_date"]),
        ("PO Reference", inv["po_number"]),
        ("Currency", inv["currency"]),
        ("Bill To", "Koda Ltd, Accounts Payable"),
    ]:
        pdf.cell(0, 6, f"{label}: {value}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    widths = [30, 74, 18, 26, 26]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(235, 231, 225)
    for w, head, align in zip(widths, ["SKU", "Description", "Qty", "Unit Price", "Amount"], "LLRRR"):
        pdf.cell(w, 8, head, border="B", align=align, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for line in inv["lines"]:
        cells = [line["sku"], line["description"], str(line["qty"]), f"{line['unit_price']:,.2f}", f"{line['amount']:,.2f}"]
        for w, text, align in zip(widths, cells, "LLRRR"):
            pdf.cell(w, 7, text, border="B", align=align)
        pdf.ln()
    pdf.ln(4)

    label_w = sum(widths[:-1])
    totals = [("Subtotal", inv["subtotal"]), (f"GST ({inv['tax_rate']:.0%})", inv["tax_amount"]), ("Total", inv["total"])]
    for label, amount in totals:
        pdf.set_font("Helvetica", "B" if label == "Total" else "", 10)
        pdf.cell(label_w, 7, f"{label}:", align="R")
        pdf.cell(widths[-1], 7, f"{amount:,.2f}", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(10)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(110)
    pdf.multi_cell(0, 4, "Payment terms: 30 days from invoice date. Please quote the invoice number with payment.\n"
                         "Generated test document - not a real invoice.")
    return bytes(pdf.output())
