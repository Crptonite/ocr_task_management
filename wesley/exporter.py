"""Navision 2013 CSV & PDF exporters for SG HQ and Vietnam Factory ERP Bridge.

Owner: Wesley (6a Part 2). Enforces strict price-confidentiality masking on Vietnam outputs.
"""
import csv
import io

from fpdf import FPDF

SG_COLUMNS = [
    "erp_entity",
    "document_type",
    "document_no",
    "external_po_no",
    "counterparty",
    "port_of_destination",
    "order_date",
    "delivery_date",
    "currency",
    "line_no",
    "sg_sku",
    "vn_bom_code",
    "description",
    "quantity",
    "price_basis",
    "customer_unit_price",
    "customer_line_amount",
    "factory_transfer_price",
    "factory_transfer_amount",
    "hq_margin",
    "plant",
    "lead_time_days",
]

VN_COLUMNS = [
    "erp_entity",
    "document_type",
    "document_no",
    "external_po_no",
    "port_of_destination",
    "order_date",
    "delivery_date",
    "currency",
    "line_no",
    "vn_bom_code",
    "sg_sku",
    "description",
    "quantity",
    "price_basis",
    "factory_transfer_price",
    "factory_transfer_amount",
    "plant",
    "lead_time_days",
]


def _safe(text: object) -> str:
    """Normalize text for FPDF core Helvetica (Latin-1)."""
    s = str(text if text is not None else "")
    for src, dst in (("\u2014", "-"), ("\u2013", "-"), ("\u2192", "->"), ("\u00b7", "|"), ("\u2022", "*")):
        s = s.replace(src, dst)
    return s.encode("latin-1", "replace").decode("latin-1")


def _fmt_num(value: float | None) -> str:
    return "" if value is None else f"{value:.2f}"


def _sg_row(bridge: dict, line: dict) -> dict:
    return {
        "erp_entity": "KODA_SG_HQ",
        "document_type": "SALES_ORDER",
        "document_no": bridge.get("order_number") or bridge.get("order_id"),
        "external_po_no": bridge.get("order_number") or "",
        "counterparty": bridge.get("buyer") or "",
        "port_of_destination": bridge.get("port") or "",
        "order_date": bridge.get("order_date") or "",
        "delivery_date": bridge.get("delivery_date") or "",
        "currency": bridge.get("currency") or "USD",
        "line_no": line["line_no"],
        "sg_sku": line.get("sku") or "",
        "vn_bom_code": line.get("vn_item_code") or "",
        "description": line.get("description") or "",
        "quantity": line.get("quantity"),
        "price_basis": "CUSTOMER_CONTRACT",
        "customer_unit_price": _fmt_num(line.get("customer_unit_price")),
        "customer_line_amount": _fmt_num(line.get("customer_amount")),
        "factory_transfer_price": _fmt_num(line.get("transfer_unit_price")),
        "factory_transfer_amount": _fmt_num(line.get("transfer_amount")),
        "hq_margin": _fmt_num(line.get("hq_margin")),
        "plant": line.get("plant") or "",
        "lead_time_days": line.get("lead_time_days") or "",
    }


def _vn_row(bridge: dict, line: dict, include_masked_cols: bool = False) -> dict:
    row = {
        "erp_entity": "KODA_VN_FACTORY",
        "document_type": "INTERNAL_FACTORY_SO",
        "document_no": bridge.get("vn_so_number"),
        "external_po_no": bridge.get("order_number") or "",
        "port_of_destination": bridge.get("port") or "",
        "order_date": bridge.get("order_date") or "",
        "delivery_date": bridge.get("delivery_date") or "",
        "currency": bridge.get("currency") or "USD",
        "line_no": line["line_no"],
        "vn_bom_code": line.get("vn_item_code") or "",
        "sg_sku": line.get("sku") or "",
        "description": line.get("description") or "",
        "quantity": line.get("quantity"),
        "price_basis": "FACTORY_TRANSFER_MASKED",
        "factory_transfer_price": _fmt_num(line.get("transfer_unit_price")),
        "factory_transfer_amount": _fmt_num(line.get("transfer_amount")),
        "plant": line.get("plant") or "",
        "lead_time_days": line.get("lead_time_days") or "",
    }
    if include_masked_cols:
        row.update({
            "counterparty": "CONFIDENTIAL (SG HQ)",
            "customer_unit_price": "MASKED",
            "customer_line_amount": "MASKED",
            "hq_margin": "MASKED",
        })
    return row


def export_navision_csv(bridge: dict, target: str = "dual") -> str:
    """Generate Navision 2013 import CSV for 'sg', 'vn', or 'dual'."""
    t = (target or "dual").strip().lower()
    if t not in ("dual", "sg", "vn"):
        raise ValueError("Target must be 'dual', 'sg', or 'vn'.")

    buf = io.StringIO()
    if t == "vn":
        writer = csv.DictWriter(buf, fieldnames=VN_COLUMNS, lineterminator="\r\n")
        writer.writeheader()
        for line in bridge.get("lines", []):
            writer.writerow(_vn_row(bridge, line, include_masked_cols=False))
        return buf.getvalue()

    writer = csv.DictWriter(buf, fieldnames=SG_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    if t in ("sg", "dual"):
        for line in bridge.get("lines", []):
            writer.writerow(_sg_row(bridge, line))
    if t == "dual":
        for line in bridge.get("lines", []):
            writer.writerow(_vn_row(bridge, line, include_masked_cols=True))
    return buf.getvalue()


def _add_sg_page(pdf: FPDF, bridge: dict) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _safe("KODA LTD (SINGAPORE HQ) - NAVISION 2013 SALES ORDER"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(95)
    pdf.cell(0, 5, _safe(f"Entity: KODA_SG_HQ | Navision Ref: {bridge.get('order_number')} | {bridge.get('transaction_id')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(4)

    for lbl, val in [
        ("Customer / Buyer", bridge.get("buyer")),
        ("Customer PO No", bridge.get("order_number")),
        ("Port of Destination", bridge.get("port")),
        ("Order / Delivery Date", f"{bridge.get('order_date') or '-'} -> {bridge.get('delivery_date') or '-'}"),
        ("Linked Vietnam SO", bridge.get("vn_so_number")),
        ("Currency", bridge.get("currency")),
    ]:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(46, 6, _safe(f"{lbl}:"))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, _safe(val), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = [26, 48, 14, 28, 28, 30]
    headers = ["SG SKU", "Description", "Qty", "Cust Price", "Transfer", "HQ Margin"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(235, 231, 225)
    for w, h, a in zip(widths, headers, "LLRRRR"):
        pdf.cell(w, 7, _safe(h), border="B", align=a, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for line in bridge.get("lines", []):
        cells = [
            line.get("sku") or "-",
            (line.get("description") or "")[:28],
            str(line.get("quantity")),
            _fmt_num(line.get("customer_unit_price")) or "-",
            _fmt_num(line.get("transfer_unit_price")) or "UNMAPPED",
            _fmt_num(line.get("hq_margin")) or "-",
        ]
        for w, c, a in zip(widths, cells, "LLRRRR"):
            pdf.cell(w, 6, _safe(c), border="B", align=a)
        pdf.ln()
    pdf.ln(4)

    cur = bridge.get("currency") or "USD"
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, _safe(f"Customer Contract Total: {cur} {_fmt_num(bridge.get('customer_total'))}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"Vietnam Transfer Total:  {cur} {_fmt_num(bridge.get('transfer_total'))}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, _safe(f"SG HQ Gross Margin:      {cur} {_fmt_num(bridge.get('hq_margin_total'))} ({bridge.get('hq_margin_pct') or 0:.1f}%)"), new_x="LMARGIN", new_y="NEXT")


def _add_vn_page(pdf: FPDF, bridge: dict) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 8, _safe("KODA VIETNAM FACTORY - INTERNAL SO & BOM SHEET"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(160, 45, 35)
    pdf.cell(0, 5, _safe("CONFIDENTIALITY BOUNDARY: CUSTOMER CONTRACT PRICES MASKED"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(3)

    for lbl, val in [
        ("Vietnam Navision SO", bridge.get("vn_so_number")),
        ("Navision Batch Ref", bridge.get("navision_doc_no")),
        ("Source SG PO Ref", bridge.get("order_number")),
        ("Port of Destination", bridge.get("port")),
        ("Target Delivery Date", bridge.get("delivery_date")),
        ("Price Basis", "Factory Transfer Price Only (Contract Price Hidden)"),
    ]:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(46, 6, _safe(f"{lbl}:"))
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 6, _safe(val), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = [28, 26, 52, 14, 26, 28]
    headers = ["VN BOM Code", "SG SKU", "Description", "Qty", "Transfer", "Line Total"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(235, 231, 225)
    for w, h, a in zip(widths, headers, "LLLRRR"):
        pdf.cell(w, 7, _safe(h), border="B", align=a, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for line in bridge.get("lines", []):
        cells = [
            line.get("vn_item_code") or "-",
            line.get("sku") or "-",
            (line.get("description") or "")[:30],
            str(line.get("quantity")),
            _fmt_num(line.get("transfer_unit_price")) or "UNMAPPED",
            _fmt_num(line.get("transfer_amount")) or "-",
        ]
        for w, c, a in zip(widths, cells, "LLLRRR"):
            pdf.cell(w, 6, _safe(c), border="B", align=a)
        pdf.ln()
    pdf.ln(4)

    cur = bridge.get("currency") or "USD"
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _safe(f"Factory Transfer Total: {cur} {_fmt_num(bridge.get('transfer_total'))}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    risk = bridge.get("lead_time_risk") or {}
    pdf.set_font("Helvetica", "B", 9)
    pdf.multi_cell(
        0,
        5,
        _safe(f"Lead-Time Risk Advisor [{str(risk.get('risk_level', '')).upper()}]: {risk.get('headline', '')}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_font("Helvetica", "", 8)
    for rec in risk.get("recommendations", [])[:3]:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(0, 5, _safe(f"- {rec}"), new_x="LMARGIN", new_y="NEXT")


def export_navision_pdf(bridge: dict, target: str = "dual") -> bytes:
    """Render Navision 2013 ERP sheet PDF for 'sg', 'vn', or 'dual'."""
    t = (target or "dual").strip().lower()
    if t not in ("dual", "sg", "vn"):
        raise ValueError("Target must be 'dual', 'sg', or 'vn'.")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(16, 16, 16)

    if t in ("sg", "dual"):
        _add_sg_page(pdf, bridge)
    if t in ("vn", "dual"):
        _add_vn_page(pdf, bridge)

    return bytes(pdf.output())
