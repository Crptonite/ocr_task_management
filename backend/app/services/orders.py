"""Order validation before ERP entry (Spectra).

Owner: Aeric (backend). Ported from legacy/opspilot/src/lib/orders.ts.
"""
import csv
import io

PRICE_DEVIATION = 0.10  # 10% from catalogue list price
AMOUNT_TOLERANCE = 0.05


def validate_order(order: dict, catalog: list[dict]) -> dict:
    issues: list[str] = []
    if not order.get("order_number"):
        issues.append("Missing order number")
    if not order.get("counterparty"):
        issues.append("Missing customer / supplier")
    if not order.get("order_date"):
        issues.append("Missing order date")
    if not order.get("delivery_date"):
        issues.append("Missing delivery date")
    elif order.get("order_date") and order["delivery_date"] < order["order_date"]:
        issues.append("Delivery date is before order date")
    lines = order.get("lines", [])
    if not lines:
        issues.append("No line items found")

    by_sku = {item["sku"].upper(): item for item in catalog}
    line_issues: list[list[str]] = []
    for line in lines:
        li: list[str] = []
        item = by_sku.get((line.get("sku") or "").upper())
        if not line.get("sku"):
            li.append("Missing SKU")
        elif item is None:
            li.append("SKU not in catalogue")
        if line["quantity"] <= 0:
            li.append("Quantity must be positive")
        if abs(line["quantity"] * line["unit_price"] - line["amount"]) > AMOUNT_TOLERANCE:
            li.append("Amount ≠ qty × price")
        if item and item["unit_price"] > 0:
            dev = (line["unit_price"] - item["unit_price"]) / item["unit_price"]
            if abs(dev) > PRICE_DEVIATION:
                li.append(f"Price {dev:+.0%} vs list {item['unit_price']:.2f}")
        line_issues.append(li)

    line_total = round(sum(line["amount"] for line in lines), 2)
    if order.get("total") is not None and abs(line_total - order["total"]) > AMOUNT_TOLERANCE:
        issues.append(f"Order total {order['total']:.2f} ≠ line total {line_total:.2f}")

    bad_lines = sum(1 for li in line_issues if li)
    if bad_lines:
        issues.append(f"{bad_lines} line(s) need attention")

    return {
        "status": "needs_attention" if issues else "ready",
        "issues": issues,
        "line_issues": line_issues,
        "line_total": line_total,
    }


def koda_entry(order: dict, catalog: list[dict]) -> dict:
    """Normalised sales-order record for keying into Koda's system.

    `ready` is only true when validation passes, so a half-read PO is never entered by accident.
    """
    validation = validate_order(order, catalog)
    names = {item["sku"].upper(): item["name"] for item in catalog}
    return {
        "ready": validation["status"] == "ready",
        "issues": validation["issues"],
        "record": {
            "customer": (order.get("counterparty") or "").strip(),
            "customer_po": order.get("order_number"),
            "order_date": order.get("order_date"),
            "requested_delivery_date": order.get("delivery_date"),
            "currency": order.get("currency"),
            "lines": [
                {
                    "line_no": i,
                    "item_no": (line.get("sku") or "").upper(),
                    "item_name": names.get((line.get("sku") or "").upper(), line.get("description")),
                    "quantity": line["quantity"],
                    "unit_price": line["unit_price"],
                    "line_amount": line["amount"],
                }
                for i, line in enumerate(order.get("lines", []), start=1)
            ],
            "total": validation["line_total"],
        },
    }


EXPORT_COLUMNS =["order_number", "type", "counterparty", "order_date", "delivery_date",
                  "currency", "line_no", "sku", "description", "quantity", "unit_price", "amount"]


def orders_to_csv(orders: list[dict]) -> str:
    """One row per line item, flat enough for a Navision / Excel import."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for order in orders:
        for i, line in enumerate(order["lines"], start=1):
            writer.writerow({
                **{k: order.get(k) for k in EXPORT_COLUMNS[:6]},
                "line_no": i,
                **{k: line.get(k) for k in EXPORT_COLUMNS[7:]},
            })
    return buf.getvalue()
