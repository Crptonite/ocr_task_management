"""Free-form invoice PDF (easyinvoicepdf-style): the user types every field instead of deriving it from a PO."""
from fpdf import FPDF

CURRENCY_SYMBOLS = {"SGD": "$", "USD": "$", "EUR": "EUR ", "GBP": "GBP "}  # core PDF fonts are latin-1 only


def invoice_totals(items: list[dict], gst_rate: float) -> dict:
    lines = [{**i, "amount": round(i["quantity"] * i["unit_price"], 2)} for i in items]
    subtotal = round(sum(l["amount"] for l in lines), 2)
    gst = round(subtotal * gst_rate, 2)
    return {"lines": lines, "subtotal": subtotal, "gst": gst, "total": round(subtotal + gst, 2)}


def render_generated_invoice(inv: dict) -> bytes:
    t = invoice_totals(inv["items"], inv["gst_rate"])
    sym = CURRENCY_SYMBOLS.get(inv["currency"], f"{inv['currency']} ")
    money = lambda v: f"{sym}{v:,.2f}"

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=20)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 12, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(110)
    pdf.cell(0, 6, f"No. {inv['invoice_number']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(6)

    top = pdf.get_y()
    bottom = top + 22
    for x, heading, name in [(18, "From", inv["seller"]), (105, "Bill to", inv["buyer"])]:
        pdf.set_xy(x, top)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(110)
        pdf.cell(80, 5, heading.upper())
        pdf.set_xy(x, top + 5)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0)
        pdf.multi_cell(80, 6, name)
        bottom = max(bottom, pdf.get_y() + 4)
    pdf.set_y(bottom)

    pdf.set_font("Helvetica", "", 10)
    for label, value in [
        ("Issue date", inv["issue_date"]),
        ("Service date", inv["service_date"]),
        ("Payment method", inv["payment_method"]),
        ("Payment date", inv["payment_date"]),
        ("Currency", f"{inv['currency']} ({sym.strip()})"),
        *([("Reference", inv["references"])] if inv.get("references") else []),
    ]:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(40, 6, label)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, str(value), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    widths = [84, 20, 35, 35]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(235, 231, 225)
    for w, head, align in zip(widths, ["Item", "Qty", "Unit price", "Amount"], "LRRR"):
        pdf.cell(w, 8, head, border="B", align=align, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for line in t["lines"]:
        cells = [line["description"][:48], f"{line['quantity']:g}", money(line["unit_price"]), money(line["amount"])]
        for w, text, align in zip(widths, cells, "LRRR"):
            pdf.cell(w, 7, text, border="B", align=align)
        pdf.ln()
    pdf.ln(4)

    label_w = sum(widths[:-1])
    for label, amount in [("Subtotal", t["subtotal"]), (f"GST ({inv['gst_rate']:.0%})", t["gst"]), ("Total", t["total"])]:
        pdf.set_font("Helvetica", "B" if label == "Total" else "", 10)
        pdf.cell(label_w, 7, f"{label}:", align="R")
        pdf.cell(widths[-1], 7, money(amount), align="R", new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())
