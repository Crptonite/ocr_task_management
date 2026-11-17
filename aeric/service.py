"""6a PO Intake: fuzzy SKU matching, field validation and the buyer clarification email.

Owner: Aeric (6a Part 1). Pure functions over plain dicts so they are easy to test;
the router wires them to the shared order catalogue and order queue.
"""
import re
from datetime import date
from difflib import SequenceMatcher
from urllib.parse import quote

from app.ai import llm

REQUIRED = {
    "po_number": "PO number",
    "buyer": "Buyer",
    "port": "Port of destination",
    "order_date": "Order date",
    "delivery_date": "Delivery date",
}
ASK_BUYER = {"port", "delivery_date", "order_date"}  # fields only the buyer can supply
PRICE_DEVIATION = 0.10


# ---------- Fuzzy SKU matcher ----------

def _norm(sku: str | None) -> str:
    return re.sub(r"[\s_]+", "", (sku or "").upper().replace("–", "-").replace("—", "-"))


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _typo_detail(given: str, right: str) -> str | None:
    if len(given) != len(right):
        return "one character missing" if len(given) < len(right) else "one extra character"
    diffs = [(i, g, r) for i, (g, r) in enumerate(zip(given, right)) if g != r]
    if len(diffs) == 1:
        i, g, r = diffs[0]
        return f"character {i + 1} is '{g}', catalogue has '{r}'"
    return None


def _by_description(description: str | None, catalog: list[dict]) -> tuple[dict | None, float]:
    if not description:
        return None, 0.0
    text = description.lower()
    best, score = None, 0.0
    for item in catalog:
        name = item["name"].lower()
        s = 1.0 if text == name else max(SequenceMatcher(None, text, name).ratio(), 0.9 if name in text or text in name else 0)
        if s > score:
            best, score = item, s
    return best, round(score, 2)


def match_sku(sku: str | None, description: str | None, catalog: list[dict]) -> dict:
    """status: exact | typo (1 char off) | near (2 chars off) | unknown | missing.

    `suggested_sku` is set whenever we have a confident catalogue candidate.
    """
    by_sku = {_norm(i["sku"]): i for i in catalog}
    given = _norm(sku)
    if not given:
        item, score = _by_description(description, catalog)
        hit = item if score >= 0.6 else None
        return {"status": "missing", "confidence": score if hit else 0.0, "distance": None,
                "suggested_sku": hit["sku"] if hit else None, "suggested_name": hit["name"] if hit else None,
                "list_price": hit["unit_price"] if hit else None,
                "message": "SKU missing" + (f"; description matches {hit['sku']}" if hit else "")}
    if given in by_sku:
        item = by_sku[given]
        return {"status": "exact", "confidence": 1.0, "distance": 0, "suggested_sku": item["sku"],
                "suggested_name": item["name"], "list_price": item["unit_price"], "message": None}
    no_dash = {k.replace("-", ""): i for k, i in by_sku.items()}
    if given.replace("-", "") in no_dash:  # "KDCH2047" -> formatting only
        item = no_dash[given.replace("-", "")]
        return {"status": "typo", "confidence": 0.97, "distance": 0, "suggested_sku": item["sku"],
                "suggested_name": item["name"], "list_price": item["unit_price"],
                "message": f"Formatting differs from {item['sku']}"}

    ranked = sorted(((levenshtein(given, k), SequenceMatcher(None, given, k).ratio(), i) for k, i in by_sku.items()),
                    key=lambda t: (t[0], -t[1]))
    if ranked:
        dist, ratio, item = ranked[0]
        tied = len(ranked) > 1 and ranked[1][0] == dist
        conf = round(max(ratio, 1 - dist / max(len(given), 1)), 2)
        if dist == 1 and not tied:
            detail = _typo_detail(given, _norm(item["sku"]))
            return {"status": "typo", "confidence": conf, "distance": 1, "suggested_sku": item["sku"],
                    "suggested_name": item["name"], "list_price": item["unit_price"],
                    "message": f"1 character off {item['sku']}" + (f" ({detail})" if detail else "")}
        if dist == 2 and len(given) >= 6 and not tied:
            return {"status": "near", "confidence": round(conf * 0.9, 2), "distance": 2, "suggested_sku": item["sku"],
                    "suggested_name": item["name"], "list_price": item["unit_price"],
                    "message": f"Close to {item['sku']} (2 characters differ)"}
    item, score = _by_description(description, catalog)
    hit = item if score >= 0.75 else None
    return {"status": "unknown", "confidence": round(score * 0.8, 2) if hit else 0.0, "distance": None,
            "suggested_sku": hit["sku"] if hit else None, "suggested_name": hit["name"] if hit else None,
            "list_price": hit["unit_price"] if hit else None,
            "message": "Not in catalogue" + (f"; description matches {hit['sku']}" if hit else "")}


# ---------- Validation ----------

def _iso(value) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def normalize_lines(lines: list[dict]) -> list[dict]:
    out = []
    for l in lines or []:
        q, p = l.get("quantity"), l.get("unit_price")
        q = None if q in ("", None) else float(q)
        p = None if p in ("", None) else float(p)
        if q is not None and q.is_integer():
            q = int(q)
        out.append({"sku": (l.get("sku") or "").strip().upper() or None,
                    "description": (l.get("description") or "").strip() or None,
                    "quantity": q, "unit_price": p,
                    "amount": round(q * p, 2) if q is not None and p is not None else None})
    return out


def validate_po(po: dict, catalog: list[dict], existing_orders: list[dict] | None = None) -> dict:
    """Field states, per-line SKU matches and a flat issue list. Errors block submission."""
    fields, issues = {}, []
    for key, name in REQUIRED.items():
        value = po.get(key)
        state, message = "ok", None
        if not value:
            state = "missing"
            message = f"{name} is missing" + (" — fill it in or ask the buyer" if key in ASK_BUYER else "")
        elif key.endswith("_date") and not _iso(value):
            state, message = "invalid", f"{name} \"{value}\" is not a date we recognise (use YYYY-MM-DD)"
        fields[key] = {"value": value, "state": state, "message": message}
        if message:
            issues.append({"level": "error", "field": key, "line": None, "code": f"{key}_{state}", "message": message})

    od, dd = po.get("order_date"), po.get("delivery_date")
    if fields["order_date"]["state"] == "ok" and fields["delivery_date"]["state"] == "ok" and dd < od:
        msg = "Delivery date is before the order date"
        fields["delivery_date"].update(state="invalid", message=msg)
        issues.append({"level": "error", "field": "delivery_date", "line": None, "code": "delivery_before_order", "message": msg})

    if not po.get("currency"):
        fields["currency"] = {"value": None, "state": "warning", "message": "Currency not stated; defaulting to USD"}
        issues.append({"level": "warning", "field": "currency", "line": None, "code": "currency_missing",
                       "message": "Currency not stated; defaulting to USD"})
    else:
        fields["currency"] = {"value": po["currency"], "state": "ok", "message": None}

    if po.get("po_number") and any(
        (o.get("order_number") or "").upper() == po["po_number"].upper()
        and (o.get("counterparty") or "").strip().lower() == (po.get("buyer") or "").strip().lower()
        for o in existing_orders or []
    ):
        msg = f"PO {po['po_number']} from this buyer is already in the order queue"
        fields["po_number"].update(state="warning", message=msg)
        issues.append({"level": "warning", "field": "po_number", "line": None, "code": "duplicate_po", "message": msg})

    lines = normalize_lines(po.get("lines") or [])
    if not lines:
        issues.append({"level": "error", "field": "lines", "line": None, "code": "no_lines",
                       "message": "No line items found — add at least one SKU"})
    checked = []
    for n, line in enumerate(lines):
        match = match_sku(line["sku"], line["description"], catalog)
        problems = []
        if match["status"] != "exact":
            problems.append({"level": "error", "code": f"sku_{match['status']}", "message": match["message"]})
        if line["quantity"] is None or line["quantity"] <= 0:
            problems.append({"level": "error", "code": "qty_invalid", "message": "Quantity must be more than 0"})
        if line["unit_price"] is None or line["unit_price"] < 0:
            problems.append({"level": "error", "code": "price_invalid", "message": "Unit price is missing"})
        elif match["status"] == "exact" and match["list_price"]:
            dev = (line["unit_price"] - match["list_price"]) / match["list_price"]
            if abs(dev) > PRICE_DEVIATION:
                problems.append({"level": "warning", "code": "price_deviation",
                                 "message": f"Price {dev:+.0%} vs list {match['list_price']:.2f}"})
        for p in problems:
            issues.append({**p, "field": "lines", "line": n,
                           "message": f"Line {n + 1} ({line['sku'] or 'no SKU'}): {p['message']}"})
        checked.append({**line, "match": match, "problems": problems})

    errors = [i for i in issues if i["level"] == "error"]
    return {
        "po": {**{k: po.get(k) for k in ("po_number", "buyer", "buyer_email", "port", "order_date", "delivery_date", "currency")},
               "lines": lines},
        "fields": fields,
        "lines": checked,
        "issues": issues,
        "status": "ready" if not errors else "needs_attention",
        "can_submit": not errors,
        "summary": {
            "lines": len(lines),
            "exact": sum(1 for l in checked if l["match"]["status"] == "exact"),
            "sku_flags": sum(1 for l in checked if l["match"]["status"] != "exact"),
            "errors": len(errors),
            "warnings": len(issues) - len(errors),
            "total": round(sum(l["amount"] or 0 for l in lines), 2),
        },
    }


# ---------- Buyer clarification email ----------

def clarification_email(result: dict, sender: str = "Koda Order Desk") -> dict:
    """Lists exactly what is missing and which SKUs disagree with the catalogue.

    Built from the validation result, so it never mentions a problem that is not on screen.
    """
    po = result["po"]
    missing = [REQUIRED[k] for k, f in result["fields"].items()
               if k in REQUIRED and f["state"] in ("missing", "invalid")]
    sku_points = []
    for n, line in enumerate(result["lines"], 1):
        m = line["match"]
        if m["status"] == "exact":
            continue
        quoted = f"\"{line['sku']}\"" if line["sku"] else "(no SKU)"
        desc = f" — {line['description']}" if line["description"] else ""
        if m["suggested_sku"]:
            sku_points.append(f"Line {n}: {quoted}{desc} is not in our catalogue. "
                              f"Did you mean {m['suggested_sku']} ({m['suggested_name']})?")
        else:
            sku_points.append(f"Line {n}: {quoted}{desc} is not in our catalogue. Please confirm the item code.")
    other = [i["message"] for i in result["issues"]
             if i["level"] == "error" and i["field"] == "lines" and i["code"] in ("qty_invalid", "price_invalid")]

    ref = po.get("po_number") or "your recent purchase order"
    buyer = po.get("buyer") or "Sourcing"
    subject = f"Clarification needed: PO {po['po_number']}" if po.get("po_number") else "Clarification needed on your purchase order"
    if po.get("buyer"):
        subject += f" ({po['buyer']})"

    parts = [f"Dear {buyer} team,", "",
             f"Thank you for {('PO ' + ref) if po.get('po_number') else ref}. Before we confirm it for production, "
             "could you please help us with the following:"]
    if missing:
        parts += ["", "Missing information:"] + [f"- {m}" for m in missing]
    if sku_points:
        parts += ["", "Item codes to confirm:"] + [f"- {s}" for s in sku_points]
    if other:
        parts += ["", "Other details:"] + [f"- {o}" for o in other]
    if not (missing or sku_points or other):
        parts += ["", "- Please confirm the order details below are correct."]
    parts += ["", "Once we have these details we will confirm the order and share the production schedule.",
              "", "Best regards,", sender]
    body = "\n".join(parts)

    generator = "template"
    if llm.llm_enabled() and (missing or sku_points):
        polished = _polish(body)
        if polished:
            body, generator = polished, "ai"

    to = po.get("buyer_email") or ""
    return {"to": to, "subject": subject, "body": body, "generator": generator,
            "points": {"missing": missing, "skus": sku_points, "other": other},
            "mailto": f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"}


def _polish(body: str) -> str | None:
    """Optional tone pass. Facts must not change; any failure keeps the template text."""
    try:
        from openai import OpenAI

        response = OpenAI(api_key=llm.api_key()).responses.create(
            model=llm.MODEL,
            instructions=("Rewrite this B2B email to be concise and courteous. Keep every bullet, item code, "
                          "field name and the sign-off exactly. Do not add new requests. Plain text only."),
            input=body,
        )
        text = (response.output_text or "").strip()
        return text or None
    except Exception:
        return None


# ---------- Demo POs ----------

SAMPLES = {
    "clean": {
        "label": "Clean multi-SKU PO (Pottery Barn)",
        "hint": "5 SKUs, every field present. Should be ready to send.",
        "text": """Pottery Barn Inc. — Purchase Order
PO Number: PB-2026-44718
Buyer: Pottery Barn Inc.
Buyer Email: sourcing@potterybarn.example
Order Date: 2026-11-10
Delivery Date: 2027-01-22
Port of Destination: Los Angeles, USA
Currency: USD

SKU | Description | Qty | Unit Price
KD-CH-2047 | Ashby oak dining chair | 120 | 145.00
KD-TB-3110 | Ashby extending dining table | 30 | 1280.00
KD-BN-1520 | Ashby oak bench 1.5m | 30 | 420.00
KD-SB-4402 | Harlow teak sideboard | 18 | 960.00
KD-ST-6031 | Linden bar stool | 64 | 118.00
""",
    },
    "missing": {
        "label": "Missing port & delivery date (Crate & Barrel)",
        "hint": "Port says TBC and no delivery date. Approval is blocked until filled.",
        "text": """Crate & Barrel — Purchase Order
PO Number: CB-77310
Buyer: Crate & Barrel
Buyer Email: orders@crateandbarrel.example
Order Date: 12/11/2026
Port of Destination: TBC
Currency: USD

SKU | Description | Qty | Unit Price
KD-CT-5208 | Harlow round coffee table | 40 | 385.00
KD-LC-7105 | Linden lounge chair | 24 | 540.00
KD-ST-6031 | Linden bar stool | 48 | 118.00
""",
    },
    "typo": {
        "label": "1-digit SKU typos (Costco)",
        "hint": "KD-CH-2041 and KD-SB-4403 are one character off the catalogue.",
        "text": """Costco Wholesale — Purchase Order
PO Number: CW-2026-0918
Buyer: Costco Wholesale
Buyer Email: furniture.buying@costco.example
Order Date: 2026-11-08
Delivery Date: 2027-02-15
Port of Destination: Seattle, USA
Currency: USD

SKU | Description | Qty | Unit Price
KD-CH-2041 | Ashby oak dining chair | 200 | 145.00
KD-TB-3110 | Ashby extending dining table | 50 | 1280.00
KD-SB-4403 | Harlow teak sideboard | 25 | 960.00
""",
    },
    "email": {
        "label": "Free-text email order (RH)",
        "hint": "No table: rules pick up 'qty x SKU @ price'. Missing port.",
        "text": """Hi Koda team,

Please book the order below.
PO Number: RH-88120
Buyer: Restoration Hardware
Order Date: 9 Nov 2026
Ship Date: 30 Jan 2027

40 x KD-LC-7105 Linden lounge chairs @ USD 540
25 x KD-CT-5208 round coffee tables @ USD 385

Thanks,
Dana Whitfield
dana.whitfield@rh.example
""",
    },
    "csv": {
        "label": "CSV export from buyer portal (West Elm)",
        "hint": "Portal CSV with metadata rows, parsed without AI.",
        "text": """PO Number,WE-55021
Buyer,West Elm
Buyer Email,vendor-ops@westelm.example
Order Date,2026-11-11
Delivery Date,2027-03-01
Port of Destination,"New York, USA"
Currency,USD
SKU,Description,Qty,Unit Price
KD-BN-1520,Ashby oak bench 1.5m,60,420.00
KD-CH-2047,Ashby oak dining chair,240,145.00
KD-TB-3110,Ashby extending dining table,60,1280.00
KD-CT-5208,Harlow round coffee table,35,385.00
""",
    },
}
