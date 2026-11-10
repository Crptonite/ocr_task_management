"""Order approval and the Review Invoice Queue (Spectra).

An approved sales order gets an invoice draft attached (`order["invoice"]`). Administrators edit the
draft's customer details and line items, then generate the invoice. Rejected orders never get a draft.
Totals are always recomputed from the lines, never trusted from the client.
"""
from datetime import date, datetime, timezone

from app.services.invoice_generator import invoice_totals

DEFAULT_TAX_RATE = 0.09  # Singapore GST


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def transaction_id(order: dict) -> str:
    return f"TXN-{order['id'].split('-')[1].zfill(5)}"


def _draft_item(line: dict, names: dict) -> dict:
    """Catalogue name as the item name; the order's wording is kept as the description only if it adds something."""
    desc = (line.get("description") or "").strip()
    name = names.get((line.get("sku") or "").upper()) or desc or line.get("sku") or "Item"
    return {"sku": line.get("sku"), "name": name, "description": "" if desc.lower() == name.lower() else desc,
            "quantity": line["quantity"], "unit_price": line["unit_price"]}


def new_invoice_draft(order: dict, catalog: list[dict]) -> dict:
    names = {item["sku"].upper(): item["name"] for item in catalog}
    return {
        "status": "pending",  # pending -> generated
        "invoice_number": f"INV-{order.get('order_number') or order['id']}",
        "customer": {"name": (order.get("counterparty") or "").strip(), "address": "", "email": ""},
        "currency": order.get("currency") or "SGD",
        "tax_rate": DEFAULT_TAX_RATE,
        "issue_date": date.today().isoformat(),
        "items": [_draft_item(line, names) for line in order.get("lines", [])],
        "updated_at": None,
        "updated_by": None,
        "generated_at": None,
        "generated_by": None,
    }


def with_totals(invoice: dict) -> dict:
    t = invoice_totals(invoice["items"], invoice["tax_rate"])
    return {**invoice, "items": t["lines"], "subtotal": t["subtotal"], "tax": t["gst"], "total": t["total"]}


def queue_entry(order: dict) -> dict:
    """What the Review Invoice Queue shows for one approved order."""
    return {
        "order_id": order["id"],
        "transaction_id": order["transaction_id"],
        "order_number": order.get("order_number"),
        "order_date": order.get("order_date"),
        "approval": order.get("approval"),
        "invoice": with_totals(order["invoice"]),
    }


def pdf_payload(order: dict, seller: str) -> dict:
    """Shape the draft for render_generated_invoice."""
    inv = order["invoice"]
    customer = inv["customer"]
    buyer = "\n".join(p for p in (customer["name"], customer.get("address"), customer.get("email")) if p)
    return {
        "invoice_number": inv["invoice_number"],
        "seller": seller,
        "buyer": buyer or "Customer",
        "issue_date": inv["issue_date"],
        "service_date": order.get("delivery_date") or inv["issue_date"],
        "payment_method": "Wire transfer",
        "payment_date": inv["issue_date"],
        "currency": inv["currency"],
        "gst_rate": inv["tax_rate"],
        "references": f"Order {order.get('order_number') or order['id']} / {order['transaction_id']}",
        "items": [
            {"description": f"{i['name']} - {i['description']}" if i["description"] and i["description"] != i["name"] else i["name"],
             "quantity": i["quantity"], "unit_price": i["unit_price"]}
            for i in inv["items"]
        ],
    }
