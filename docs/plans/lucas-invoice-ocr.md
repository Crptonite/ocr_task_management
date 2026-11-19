# AI Coding Plan: Lucas — Module 6b (Part 1) Invoice OCR Extraction & Document Generators

**Owner:** Lucas (6b Part 1 — OCR / OpenAI Extraction, Invoice Review Queue & Test Document Generators)  
**Module:** Problem Statement 6b (AI Invoice & Document Checking)

---

## 1. Problem & Business Context
From `docs/meetings/2026-11-05-koda-client-briefing.md`:
- Koda staff cross-check supplier and shipping invoices against Purchase Orders (POs) and handle scanned PDFs/photos without paying File.ai's high monthly minimum subscription.
- The system needs lightweight PDF text-layer + regex extraction first (`0` AI tokens), falling back to OpenAI Vision only when the document is scanned or key fields are unreadable, plus a camera scanner and realistic test invoice/receipt generators for live walkthroughs.

## 2. Solution Architecture
- `backend/app/ai/extractor.py` — Rules-first PDF text-layer (`pypdf`) and regex extractor for invoices (`extract_invoice`, `parse_invoice_text`) and orders (`extract_order`, `parse_order_text`), recording confidence and missing fields.
- `backend/app/ai/llm.py` — Structured-output OpenAI Vision/PDF fallback (`read_invoice`, `read_order`) guarded by `OPENAI_API_KEY`.
- `backend/app/services/autofill.py` — Completes partial OCR drafts with traceable `INV-AUTO-` / `PO-AUTO-` markers and flags them for human review.
- `backend/app/services/invoice_pdf.py` & `backend/app/services/invoice_generator.py` — `fpdf2` PDF generators (`clean`, `price`, `qty`, `tax` variants plus multi-currency custom invoices).
- `backend/app/routers/invoices.py`, `backend/app/routers/invoice_generator.py`, `frontend/js/scanner.js`, `frontend/invoice-generator.html`, `frontend/receipt_invoice_generator.html` — Upload, camera scan (`Scanner.open()`), Review Queue UI, and standalone test document designers.
- `backend/tests/test_llm_extraction.py`, `test_autofill.py`, `test_invoice_pdf.py`, `test_invoice_generator.py` — Automated pytest coverage for regex-first priority, OpenAI scan fallback, error handling without API keys, and PDF generation.
