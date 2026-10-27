"""Invoice extraction (OCR / LLM).

Owner: Lucas (OCR & AI). Replace `extract_invoice` with the real pipeline
(PDF text / OCR -> LLM -> validated JSON). Keep the return shape the same so
the matching engine and frontend keep working.
"""


def extract_invoice(filename: str, content: bytes) -> dict:
    # Placeholder: returns an empty draft for staff to fill in.
    return {
        "invoice_number": None,
        "po_number": None,
        "supplier": None,
        "invoice_date": None,
        "currency": None,
        "tax_rate": 0.0,
        "tax_amount": 0.0,
        "lines": [],
        "source_file": filename,
        "size_bytes": len(content),
        "confidence": 0.0,
        "note": "Extraction not implemented yet",
    }

