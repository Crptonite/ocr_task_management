# Koda AI Operations Workspace

Integrated AI-assisted **Purchase Order (PO) & Invoice Operations** platform for **Koda Ltd** (SCCCI × NYP AI Innovation Challenge, IT2134 — Problem Statements **6a** & **6b**, plus **6c** Planning & Project Tracking).

## End-to-End Workflow

1. **6a Part 1 — Customer PO Intake & Validation (`aeric/`, `#orders/intake`):** Upload PDF, CSV, text, pasted email, or camera scan (`Scanner.open()`). Rules-first parser (`0` AI tokens) + optional Tesseract OCR + OpenAI Vision fallback extracts fields, catches 1-character SKU typos via Levenshtein fuzzy matching, drafts buyer clarification emails, and queues verified POs.
2. **Order Queue (`backend/app/routers/orders.py`, `#orders/queue`):** Staff inspect, edit, approve, or reject queued orders.
3. **6a Part 2 — SG–VN ERP Bridge (`wesley/`, `#orders/bridge`):** Converts approved Singapore HQ orders into Vietnam Factory SOs with strict SG vs. Vietnam customer contract price masking, inline transfer-price mapping, lead-time risk advisories, and Dual Navision 2013 CSV/PDF exports.
4. **6b Part 1 — Invoice OCR, Review Queue & Generators (`backend/app/`, `#invoices/queue`):** Extracts uploaded supplier invoices (PDF text/regex + OpenAI Vision fallback), auto-fills partial drafts, manages generated invoices for approved orders, and provides test PDF/receipt designers (`/invoice-generator`, `/receipt-generator`).
5. **6b Part 2 — 3-Way Match & Approval (`qizhi/`, `#invoices/three-way-match`):** Compares Invoice vs. PO vs. hard-copy POS receipt (wrapped lines, decimal commas, derived unit-price rounding tolerance), renders a side-by-side diff matrix, generates departmental tasks (optional Claude wording via `ANTHROPIC_API_KEY`), enforces department-head segregation-of-duties approval, and verifies a SHA-256 hash-chained audit trail.

## Team & Project Structure

| Member | Scope | Package / Directory |
| --- | --- | --- |
| **Aeric (Lead)** | 6a Part 1 — PO Intake, Fuzzy SKU Matching & Order Queue | `aeric/` |
| **Wesley** | 6a Part 2 — SG–VN ERP Bridge, Price Masking & Navision 2013 Export | `wesley/` |
| **Lucas** | 6b Part 1 — OCR / OpenAI Extraction, Scanner, Review Queue, DB & Generators | `backend/app/`, `frontend/` |
| **Qizhi** | 6b Part 2 — 3-Way Match, Receipt Parser, Tasks, Approval & Audit Chain | `qizhi/` |

```text
aeric/            6a Part 1 router, parser, fuzzy matcher, intake JS & pytest tests
wesley/           6a Part 2 router, transfer pricing, Navision CSV/PDF exporter & tests
qizhi/            6b Part 2 router, 3-way matcher, receipt parser, store, UI JS & tests
backend/
  app/
    main.py       Unified FastAPI entrypoint (mounts /api/*, /aeric, /wesley, /qizhi, /)
    routers/      Core routers (documents, orders, invoices, invoice_queue, invoice_generator, projects, planning)
    services/     Validation, matching, autofill, PDF generation, Supabase & CSV sync
    ai/           pypdf/regex extractors and OpenAI structured-output Vision fallback
    models.py     SQLAlchemy models (SQLite or Supabase Postgres)
    database.py   Startup load + request-level persistence
  tests/          Core backend pytest suite
frontend/         Hash-routed vanilla HTML/CSS/JS SPA (light & dark mode, Montserrat)
docs/             architecture.md (flow, ERD, API), plans/, meetings/, distinction-checklist.md
vercel.json       Copies feature JS slices into frontend/ for static Vercel builds
```

## Setup & Local Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` (app) or `http://127.0.0.1:8000/docs` (OpenAPI docs).

### Environment Variables (`backend/.env.example`)

Copy `backend/.env.example` to `backend/.env` as needed (everything is optional; the app starts cleanly with defaults):

- `DATABASE_URL` — Unset = local SQLite (`backend/koda.db`), `off` = in-memory only, or a Supabase Postgres Session Pooler URL (`workspace` schema).
- `OPENAI_API_KEY` / `OPENAI_MODEL` — Enables OpenAI Vision/text fallback for scanned photos and unfamiliar PO/invoice layouts.
- `NEXT_PUBLIC_SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` — Optional Supabase Storage backup for uploaded invoice PDFs.
- `ANTHROPIC_API_KEY` — Optional Claude wording refinement for 3-way match discrepancy tasks.
- `TESSERACT_CMD` — Optional path to local Tesseract binary for scanned receipt/PO OCR (`tesseract` + `poppler` for scanned PDFs).

## Verification

```bash
cd backend
.\.venv\Scripts\pytest.exe -q
```

Syntax check frontend JS modules:

```bash
node --check frontend/js/app.js
node --check frontend/js/scanner.js
node --check aeric/po_intake.js
node --check wesley/erp_bridge.js
node --check qizhi/three_way_match.js
```

## Cloud Deployment

- **Frontend (Vercel):** Deployed from `frontend/` using `vercel.json` (`buildCommand` copies `aeric/po_intake.js`, `wesley/erp_bridge.js`, and `qizhi/three_way_match.js` into `frontend/`).
- **Backend (FastAPI host):** Run `uvicorn app.main:app --host 0.0.0.0 --port $PORT` from `backend/` (with `PYTHONPATH=.:..` or repo root on path so `aeric`, `wesley`, and `qizhi` resolve). When frontend and backend are on separate origins, point the frontend to the backend via `localStorage.setItem("koda-api", "https://<your-backend-url>")`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for Git workflow and [docs/architecture.md](docs/architecture.md) for the ERD and API reference.
