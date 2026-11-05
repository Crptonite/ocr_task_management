"""Saves uploaded invoices (the PDF and the extracted row) to Supabase.

Owner: Lucas (OCR & AI). Talks to Supabase's REST and Storage APIs with the service-role key,
so it must only run server-side. Without NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
(environment or backend/.env) everything here is off and the app keeps its in-memory store.
Run backend/supabase/koda_invoices.sql once in the project's SQL editor to create the table and bucket.
"""
import os
import re
import uuid
from pathlib import Path

import httpx

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
BUCKET = "documents"
TABLE = "koda_invoices"
ROW_FIELDS = ("invoice_number", "po_number", "supplier", "invoice_date", "currency", "tax_rate", "tax_amount", "lines", "source_file")


def _env(name: str) -> str | None:
    """From the environment, else backend/.env (only the named key is read)."""
    value = os.environ.get(name)
    if not value and ENV_FILE.exists():
        try:
            from dotenv import dotenv_values

            value = dotenv_values(ENV_FILE).get(name)
        except ImportError:
            pass
    return value.strip() or None if value else None


def enabled() -> bool:
    return bool(_env("NEXT_PUBLIC_SUPABASE_URL") and _env("SUPABASE_SERVICE_ROLE_KEY"))


def _base() -> str:
    return _env("NEXT_PUBLIC_SUPABASE_URL").rstrip("/")


def _headers(**extra: str) -> dict:
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    return {"apikey": key, "Authorization": f"Bearer {key}", **extra}


def _check(res: httpx.Response) -> httpx.Response:
    if res.status_code >= 400:
        raise RuntimeError(f"Supabase {res.status_code}: {res.text[:200]}")
    return res


def upload_file(filename: str, content: bytes) -> str:
    """Store the document in the private bucket and return its path."""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "invoice.pdf"
    path = f"invoices/{uuid.uuid4().hex[:12]}-{safe}"
    mime = "application/pdf" if content.startswith(b"%PDF") else "application/octet-stream"
    _check(httpx.post(f"{_base()}/storage/v1/object/{BUCKET}/{path}", content=content,
                      headers=_headers(**{"Content-Type": mime}), timeout=30))
    return path


def signed_url(path: str, expires: int = 300) -> str:
    """Short-lived link that opens the stored file in a browser."""
    res = _check(httpx.post(f"{_base()}/storage/v1/object/sign/{BUCKET}/{path}", json={"expiresIn": expires},
                            headers=_headers(), timeout=15))
    return f"{_base()}/storage/v1{res.json()['signedURL']}"


def save_invoice(invoice: dict, file_path: str | None) -> None:
    row = {k: invoice.get(k) for k in ROW_FIELDS} | {"file_path": file_path}
    _check(httpx.post(f"{_base()}/rest/v1/{TABLE}", json=row, headers=_headers(Prefer="return=minimal"), timeout=15))


def load_invoices() -> list[dict]:
    res = _check(httpx.get(f"{_base()}/rest/v1/{TABLE}?select=*&order=created_at.asc", headers=_headers(), timeout=15))
    return [{k: r.get(k) for k in (*ROW_FIELDS, "file_path")} for r in res.json()]


def delete_file(path: str) -> None:
    _check(httpx.request("DELETE", f"{_base()}/storage/v1/object/{BUCKET}", json={"prefixes": [path]},
                         headers=_headers(), timeout=15))


def delete_invoice(invoice_number: str, file_path: str | None) -> None:
    _check(httpx.delete(f"{_base()}/rest/v1/{TABLE}", params={"invoice_number": f"eq.{invoice_number}"},
                        headers=_headers(), timeout=15))
    if file_path:
        delete_file(file_path)
