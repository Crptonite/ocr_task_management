"""AI Discrepancy Task Suggester.

Layer 1 (always on, deterministic): rules turn each discrepancy group into a task with an owner
department, priority, due date, concrete next action and whether a dept-head approval is needed.
Layer 2 (optional): if ANTHROPIC_API_KEY is set and the `anthropic` package is installed, Claude rewrites
the wording using the invoice context. It can ONLY change text fields, never owner/priority/approval,
so a bad model response can't alter routing or bypass approval. Any failure falls back to layer 1.
"""
import json
import os
from decimal import Decimal

from qizhi.money import D

APPROVAL_THRESHOLD = Decimal(os.getenv("APPROVAL_THRESHOLD", "100"))

# kind: (department, title, suggested action, due in days, always needs dept-head approval)
RULES = {
    "MISSING_PO":          ("Procurement", "Find or raise a PO for this invoice",
                            "Ask the requester which PO covers this spend. If none exists, raise a retrospective PO "
                            "(needs dept-head approval) before the invoice is posted.", 2, True),
    "PO_NOT_FOUND":        ("Procurement", "Resolve unknown PO number",
                            "Check for a typo on the invoice, then confirm the PO number with the vendor.", 2, True),
    "PRICE_MISMATCH":      ("Procurement", "Resolve unit price difference",
                            "Confirm the agreed price with the vendor. Request a credit note or corrected invoice; "
                            "if the new price is legitimate, get a PO amendment approved.", 3, False),
    "QTY_MISMATCH":        ("Warehouse", "Verify quantity billed vs ordered/received",
                            "Check the goods-received note or count stock. Short-delivered: ask for a credit note. "
                            "Over-delivered: return or approve the extra.", 3, False),
    "LINE_NOT_ON_PO":      ("Procurement", "Billed item is not on the PO",
                            "Confirm whether this was an authorised add-on. Reject the line or amend the PO.", 2, True),
    "LINE_NOT_ON_RECEIPT": ("Warehouse", "Billed item has no receipt",
                            "Confirm the goods were physically received before paying for this line.", 2, False),
    "ORDERED_NOT_BILLED":  ("Procurement", "Ordered item missing from invoice",
                            "Likely a back-order. Confirm delivery status and keep the PO line open.", 5, False),
    "RECEIVED_NOT_BILLED": ("Finance", "Received item missing from invoice",
                            "Ask the vendor to bill the item or confirm it was a free sample.", 5, False),
    "VENDOR_MISMATCH":     ("Finance", "Vendor name differs from PO",
                            "Check for a changed legal entity or a possible fraudulent invoice before paying.", 1, True),
    "TOTAL_MISMATCH":      ("Finance", "Invoice totals do not reconcile",
                            "Recalculate the totals; ask the vendor for a corrected invoice.", 3, False),
    "TAX_MISMATCH":        ("Finance", "Tax differs from receipt",
                            "Check tax rate/exemption status and request a corrected tax invoice if needed.", 3, False),
    "PO_TOTAL_MISMATCH":   ("Procurement", "Invoice total differs from the PO",
                            "Compare the invoice with the PO line by line. Over-billed: ask for a credit note or "
                            "corrected invoice. If the extra cost is legitimate, get a PO amendment approved.", 3, False),
    "INVOICE_BEFORE_PO":   ("Procurement", "Invoice is dated before the PO",
                            "Find out why work was billed before it was ordered. If it was a retrospective order, "
                            "record the reason and get dept-head approval before paying.", 2, True),
    "INVOICE_LATE":        ("Finance", "Invoice arrived long after the PO",
                            "Confirm the delivery date and that the invoice has not been paid or billed twice.", 5, False),
    "PO_EXPIRED":          ("Procurement", "PO had expired by the invoice date",
                            "Ask Procurement to extend the PO or confirm the order was still valid.", 2, True),
    "INVOICE_DATE_FUTURE": ("Finance", "Invoice is dated in the future",
                            "Ask the vendor to correct the date; likely a typing error.", 2, False),
    "INVOICE_DATE_MISSING": ("AP", "Invoice date missing or unreadable",
                            "Check the original invoice and enter the date, or ask the vendor for a corrected copy.", 2, False),
    "LINE_MATH":           ("Finance", "Line arithmetic is wrong",
                            "Qty x unit price does not equal the line total. Ask the vendor to reissue.", 3, False),
    "RECEIPT_OCR_UNRELIABLE": ("AP", "Re-scan the receipt",
                            "The receipt's own totals do not add up, so OCR probably misread a number.", 1, False),
}
PRIORITY = {"critical": "P1", "high": "P2", "medium": "P3", "low": "P4"}
ORDER = ["low", "medium", "high", "critical"]


def suggest_tasks(result: dict) -> list[dict]:
    """Group discrepancies by (type, line) and produce one suggestion per group."""
    groups = {}
    for d in result["discrepancies"]:
        groups.setdefault((d["type"], d["line_key"]), []).append(d)

    out = []
    for (kind, line_key), ds in groups.items():
        dept, title, action, due, always_approval = RULES.get(
            kind, ("AP", f"Review {kind}", "Review manually.", 3, False))
        sev = max((d["severity"] for d in ds), key=ORDER.index)
        impact = max((abs(D(d["variance"], Decimal(0))) for d in ds), default=Decimal(0))
        where = "" if line_key == "header" else f" (line {ds[0].get('line_no') or line_key})"
        out.append({
            "group_key": f"{kind}|{line_key}",
            "title": f"{title}{where}",
            "description": " ".join(d["message"] for d in ds),
            "suggested_action": action,
            "department": dept,
            "priority": PRIORITY[sev],
            "severity": sev,
            "impact": str(impact),
            "due_in_days": due,
            "requires_approval": always_approval or impact >= APPROVAL_THRESHOLD,
            "discrepancy_ids": [d["id"] for d in ds],
            "type": kind,
            "ai_refined": False,
        })
    out.sort(key=lambda s: (s["priority"], -Decimal(s["impact"])))
    return llm_refine(result, out)


def llm_refine(result: dict, suggestions: list[dict]) -> list[dict]:
    if not os.getenv("ANTHROPIC_API_KEY") or not suggestions:
        return suggestions
    try:
        import anthropic  # optional dependency
        client = anthropic.Anthropic()
        payload = [{"i": i, "type": s["type"], "department": s["department"], "facts": s["description"],
                    "draft_action": s["suggested_action"]} for i, s in enumerate(suggestions)]
        msg = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"), max_tokens=1500,
            system=("You help accounts-payable clerks. For each item rewrite 'title' (max 8 words) and "
                    "'action' (max 2 sentences, concrete, name who to contact and what to ask for). "
                    "Use only the facts given; do not invent amounts or names. "
                    "Return ONLY a JSON array of {i,title,action}."),
            messages=[{"role": "user", "content": f"Vendor: {result.get('vendor')}; invoice "
                                                    f"{result['invoice_no']}.\n{json.dumps(payload)}"}])
        text = "".join(b.text for b in msg.content if b.type == "text").strip()
        text = text.removeprefix("```json").removesuffix("```").strip()
        for item in json.loads(text):
            s = suggestions[int(item["i"])]
            if isinstance(item.get("title"), str) and isinstance(item.get("action"), str):
                where = s["title"][s["title"].find(" ("):] if " (" in s["title"] else ""
                s["title"], s["suggested_action"], s["ai_refined"] = item["title"][:80] + where, item["action"][:400], True
    except Exception:
        pass            # fall back silently to rule-based text
    return suggestions
