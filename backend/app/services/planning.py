"""Material requirements, shortage detection and production priorities.

Owner: Lucas (AI / planning). Deterministic and explainable on purpose: a planner
has to be able to see why an order was ranked where it was.

How it works:
  1. Explode each customer order through the product's bill of materials.
  2. Walk the orders earliest-due first and try to cover each one in full from
     stock, then from inbound supplier deliveries that land on or before its due date.
  3. An order that cannot be covered in full reserves nothing, so it cannot starve
     a later order that could have shipped. It is reported as short instead.
"""
from datetime import date

URGENT_DAYS = 3   # due this soon -> urgent
WATCH_DAYS = 7    # a shortage this close to the due date is escalated


def _days_between(later: str, earlier: date) -> int:
    return (date.fromisoformat(later) - earlier).days


def requirements(order: dict, products: dict) -> dict[str, float]:
    bom = products[order["product"]]["bom"]
    return {sku: round(per_unit * order["quantity"], 4) for sku, per_unit in bom.items()}


def plan(data: dict, today: date | None = None) -> dict:
    today = today or date.today()
    products, materials = data["products"], data["materials"]
    stock = {sku: m["on_hand"] for sku, m in materials.items()}
    inbound = sorted(({**row, "left": row["qty"]} for row in data["inbound"]), key=lambda r: r["eta"])

    def inbound_for(sku: str, by: str | None = None) -> list[dict]:
        return [r for r in inbound if r["sku"] == sku and r["left"] > 0 and (by is None or r["eta"] <= by)]

    orders = []
    for order in sorted(data["demand"], key=lambda o: (o["due_date"], o["order_number"])):
        if order["product"] not in products:
            orders.append({**order, "status": "unknown_product", "priority": "high",
                           "days_to_due": _days_between(order["due_date"], today),
                           "shortages": [], "start_after": None, "buildable_units": 0,
                           "action": f"Product {order['product']} has no bill of materials"})
            continue

        need = requirements(order, products)
        shortages = []
        for sku, qty in need.items():
            from_stock = min(stock.get(sku, 0), qty)
            from_inbound = sum(r["left"] for r in inbound_for(sku, order["due_date"]))
            short_by = round(qty - from_stock - min(qty - from_stock, from_inbound), 4)
            if short_by > 0:
                shortages.append(_shortage(sku, materials, qty, short_by, stock, inbound_for(sku)))

        start_after = None
        if not shortages:
            for sku, qty in need.items():
                take = min(stock.get(sku, 0), qty)
                stock[sku] = round(stock.get(sku, 0) - take, 4)
                rest = qty - take
                for r in inbound_for(sku, order["due_date"]):
                    if rest <= 0:
                        break
                    used = min(r["left"], rest)
                    r["left"] -= used
                    rest -= used
                    start_after = max(start_after or r["eta"], r["eta"])
            status = "inbound" if start_after else "ready"
        else:
            status = "short"

        days = _days_between(order["due_date"], today)
        orders.append({
            **order,
            "product_name": products[order["product"]]["name"],
            "requirements": need,
            "status": status,
            "start_after": start_after,
            "days_to_due": days,
            "priority": _priority(status, days),
            "shortages": shortages,
            "buildable_units": _buildable(order, products, stock, inbound) if status == "short" else order["quantity"],
        })

    return {
        "as_of": today.isoformat(),
        "orders": orders,
        "sequence": _sequence(orders),
        "materials": _material_summary(data, orders),
        "purchase_suggestions": _purchase_suggestions(orders),
        "summary": {
            "orders": len(orders),
            "ready": sum(o["status"] == "ready" for o in orders),
            "inbound": sum(o["status"] == "inbound" for o in orders),
            "short": sum(o["status"] in ("short", "unknown_product") for o in orders),
        },
    }


def _shortage(sku: str, materials: dict, needed: float, short_by: float, stock: dict, later_inbound: list[dict]) -> dict:
    """What is missing, and the first delivery date (if any) that would close the gap."""
    covered, cover_date = stock.get(sku, 0), None
    for r in later_inbound:
        covered += r["left"]
        if covered >= needed:
            cover_date = r["eta"]
            break
    return {
        "sku": sku,
        "name": materials.get(sku, {}).get("name", sku),
        "needed": needed,
        "short_by": short_by,
        "covered_from": cover_date,  # None: no scheduled delivery closes it, a new PO is needed
    }


def _buildable(order: dict, products: dict, stock: dict, inbound: list[dict]) -> int:
    """Units that could ship on time from what is left after the orders ahead of it."""
    units = order["quantity"]
    for sku, per_unit in products[order["product"]]["bom"].items():
        have = stock.get(sku, 0) + sum(r["left"] for r in inbound if r["sku"] == sku and r["eta"] <= order["due_date"])
        units = min(units, int(have // per_unit))
    return max(units, 0)


def _priority(status: str, days_to_due: int) -> str:
    if status == "short":
        return "urgent" if days_to_due <= WATCH_DAYS else "high"
    if days_to_due <= URGENT_DAYS:
        return "urgent"
    return "high" if status == "inbound" else "normal"


def _sequence(orders: list[dict]) -> list[dict]:
    """Build order: what can start now (earliest due first), then what waits on a delivery, then blocked jobs."""
    tier = {"ready": 0, "inbound": 1}
    buildable = [o for o in orders if o["status"] in tier]
    buildable.sort(key=lambda o: (tier[o["status"]], o["start_after"] or "", o["due_date"]))
    blocked = [o for o in orders if o["status"] not in tier]
    steps = []
    for rank, o in enumerate(buildable + blocked, start=1):
        steps.append({"rank": rank, "order_number": o["order_number"], "customer": o["customer"],
                      "due_date": o["due_date"], "priority": o["priority"], "status": o["status"],
                      "action": o.get("action") or _action(o)})
    return steps


def _action(o: dict) -> str:
    if o["status"] == "ready":
        return "Start now: all materials in stock"
    if o["status"] == "inbound":
        return f"Start from {o['start_after']}: waiting on a supplier delivery"
    parts = []
    for s in o["shortages"]:
        fix = f"arrives {s['covered_from']}, too late" if s["covered_from"] else "no delivery scheduled"
        parts.append(f"{s['sku']} short {s['short_by']:g} ({fix})")
    msg = "Blocked: " + "; ".join(parts)
    if o["buildable_units"] > 0:
        msg += f". Could ship {o['buildable_units']} of {o['quantity']} on time"
    return msg


def _material_summary(data: dict, orders: list[dict]) -> list[dict]:
    required = dict.fromkeys(data["materials"], 0.0)
    for o in orders:
        for sku, qty in o.get("requirements", {}).items():
            required[sku] = required.get(sku, 0.0) + qty
    rows = []
    for sku, m in data["materials"].items():
        inbound = sum(r["qty"] for r in data["inbound"] if r["sku"] == sku)
        gap = round(required[sku] - m["on_hand"], 4)
        shortfall = round(max(0.0, gap - inbound), 4)
        rows.append({
            "sku": sku, "name": m["name"], "unit": m["unit"],
            "required": round(required[sku], 4), "on_hand": m["on_hand"], "inbound": inbound,
            "shortfall": shortfall,
            "status": "short" if shortfall > 0 else ("needs_inbound" if gap > 0 else "ok"),
        })
    return rows


def _purchase_suggestions(orders: list[dict]) -> list[dict]:
    """Per material, the smallest order that unblocks the short jobs, with the date it is needed by."""
    by_sku: dict[str, dict] = {}
    for o in orders:
        if o["status"] != "short":
            continue
        for s in o["shortages"]:
            row = by_sku.setdefault(s["sku"], {"sku": s["sku"], "name": s["name"], "buy_qty": 0.0,
                                               "needed_by": o["due_date"], "for_orders": []})
            row["buy_qty"] = round(row["buy_qty"] + s["short_by"], 4)
            row["needed_by"] = min(row["needed_by"], o["due_date"])
            row["for_orders"].append(o["order_number"])
    return sorted(by_sku.values(), key=lambda r: r["needed_by"])
