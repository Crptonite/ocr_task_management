"""Glue between the 3-way-match engine and the rest of the app: PO lookup, existing-invoice adapter, match run."""
from app import store as app_store
from app.services.invoice_queue import with_totals
from qizhi import store as tw_store
from qizhi.matching import match_invoice
from qizhi.receipt_parser import parse_receipt_text, receipt_to_json
from qizhi.sample_data import PO_REGISTER
from qizhi.suggester import suggest_tasks

store = tw_store.Store()


def _po_from_erp(po: dict) -> dict:
    """Koda ERP purchase order -> the shape the matcher expects."""
    return {"po_number": po["po_number"], "vendor": po.get("supplier", ""), "po_date": po.get("po_date"),
            "valid_until": po.get("valid_until"), "lines": po.get("lines", [])}


def _po_from_order(order: dict) -> dict:
    """Approved/queued customer order -> the shape the matcher expects."""
    lines = [{"sku": l.get("sku") or "", "description": l.get("description") or "",
              "qty": l["quantity"], "unit_price": l["unit_price"]} for l in order.get("lines", [])]
    return {"po_number": order.get("order_number") or order["id"], "vendor": order.get("counterparty", ""),
            "po_date": order.get("order_date"), "valid_until": order.get("delivery_date"), "lines": lines}


def find_po(po_number: str | None) -> dict | None:
    """Demo register first, then ERP POs, then queued/approved customer orders."""
    po_number = (po_number or "").strip()
    if not po_number:
        return None
    if po_number in PO_REGISTER:
        return PO_REGISTER[po_number]
    erp = next((p for p in app_store.erp.get("purchase_orders", []) if p["po_number"] == po_number), None)
    if erp:
        return _po_from_erp(erp)
    order = next((o for o in app_store.orders.get("orders", [])
                  if (o.get("order_number") or o["id"]) == po_number), None)
    return _po_from_order(order) if order else None


def erp_invoices() -> list[dict]:
    """Invoices already in the Review Queue (supplier ERP invoices + approved order drafts)."""
    out = []
    for inv in app_store.erp.get("invoices", []):
        lines = [{"sku": l.get("sku", ""), "description": l.get("description", ""), "qty": l["qty"],
                  "unit_price": l["unit_price"]} for l in inv.get("lines", [])]
        subtotal = round(sum(l["qty"] * l["unit_price"] for l in lines), 2)
        tax = round(inv.get("tax_amount") or 0.0, 2)
        out.append({"invoice_no": inv["invoice_number"], "vendor": inv.get("supplier", ""),
                    "po_number": inv.get("po_number") or "", "date": inv.get("invoice_date"),
                    "lines": lines, "subtotal": subtotal, "tax_rate": inv.get("tax_rate"),
                    "tax": tax, "total": round(subtotal + tax, 2)})
    for o in app_store.orders.get("orders", []):
        if "invoice" not in o:
            continue
        inv = with_totals(o["invoice"])
        lines = [{"sku": i.get("sku") or "", "description": i.get("description") or i["name"],
                  "qty": i["quantity"], "unit_price": i["unit_price"]} for i in inv["items"]]
        out.append({"invoice_no": inv["invoice_number"], "vendor": inv["customer"]["name"],
                    "po_number": o.get("order_number") or o["id"], "date": inv["issue_date"],
                    "lines": lines, "subtotal": inv["subtotal"], "tax_rate": inv["tax_rate"],
                    "tax": inv["tax"], "total": inv["total"]})
    return out


def run_match(invoice: dict, receipt_text: str | None, user: dict, create_tasks: bool = True) -> dict:
    receipt = parse_receipt_text(receipt_text) if receipt_text and receipt_text.strip() else None
    result = match_invoice(invoice, find_po(invoice.get("po_number")), receipt)
    result["receipt"] = receipt_to_json(receipt) if receipt else None
    result["suggestions"] = suggest_tasks(result)
    store.log(user, "INVOICE_MATCHED", None, result["invoice_no"], status=result["status"],
              discrepancies=result["summary"]["discrepancies"], po_found=result["po_found"])
    result["tasks"] = []
    if create_tasks:
        for s in result["suggestions"]:
            task, is_new = store.create_task(user, result["invoice_no"], s)
            result["tasks"].append({"task_id": task["id"], "new": is_new})
    store.save_result(result["invoice_no"], result)
    return result
