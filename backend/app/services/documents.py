"""One combined list of invoices and orders, mirrored to a CSV file that is rewritten on every change."""
import csv
from pathlib import Path

from app import store

CSV_PATH = Path(__file__).resolve().parents[1] / "data" / "documents.csv"
COLUMNS = ["Document", "Type", "Company", "Date", "Amount", "Status"]


def build_documents() -> list[dict]:
    # Imported here: the routers import this module to call sync_csv() after each change.
    from app.routers.invoices import list_invoices
    from app.routers.orders import with_validation

    rows = []
    for inv in list_invoices():
        rows.append({
            "Document": inv["invoice_number"], "Type": "Invoice", "Company": inv["supplier"],
            "Date": inv.get("invoice_date") or "", "Amount": f"{inv['total']:.2f}",
            "Currency": inv.get("currency", ""), "Status": inv["match"]["status"],
        })
    for order in store.orders["orders"]:
        o = with_validation(order)
        status = o["validation"]["status"] if o["status"] == "extracted" else o["status"]
        rows.append({
            "Document": o.get("order_number") or o["id"], "Type": f"{(o.get('type') or '').title()} order".strip(),
            "Company": o.get("counterparty") or "", "Date": o.get("order_date") or "",
            "Amount": "" if o.get("total") is None else f"{o['total']:.2f}",
            "Currency": o.get("currency", ""), "Status": status,
        })
    return rows


def sync_csv() -> None:
    """Rewrite the CSV from the current in-memory state. Never lets a disk problem break the request."""
    try:
        rows = build_documents()
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS + ["Currency"])
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        print(f"documents.csv not updated: {exc}")
