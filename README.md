# Koda Invoice Check

AI-assisted invoice checking for **Koda Ltd** (Problem Statement 6b, SCCCI × NYP AI Innovation Challenge, IT2134).

Staff upload a supplier invoice → the system extracts the fields → matches them against the purchase order → flags price, quantity, tax and duplicate issues → staff approve and export for Dynamics.

The same workspace also has tabs for two related problem statements:

- **Orders (Spectra Innovations):** extract purchase / sales orders, validate line items against the catalogue, approve, export CSV for ERP entry.
- **Projects (EM Services):** projects broken into tasks with owners and deadlines, a task board, filters, overdue summary and AI task suggestions.
- **Planning (Koda):** customer orders exploded into materials, checked against stock and inbound deliveries, with shortage alerts, a suggested build order and purchase suggestions (`GET /api/planning`).

Customer PO upload (`POST /api/orders/upload`) reads customer, product lines, quantities and delivery date from the PDF text layer and validates them. `GET /api/orders/{id}/koda-entry` returns the normalised record for Koda entry.

## Team

| Member | Role | Owns |
| --- | --- | --- |
| Aeric (lead) | Backend & architecture | `backend/app/` (API, matching, data) |
| Qizhi | Frontend | `frontend/` |
| Lucas | OCR & AI | `backend/app/ai/` |
| Wesley | Testing & QA | `backend/tests/`, `.github/workflows/` |

## Project structure

```
backend/
  app/
    main.py            FastAPI app + serves the frontend
    routers/           API per tab: invoices, orders, projects
    services/          rules: invoice matching, order validation, project progress
    ai/                extraction (OCR / LLM) and task suggestions
    data/              mock data (ERP, orders, projects)
    store.py           in-memory store until Supabase
  tests/               pytest
frontend/              static HTML / CSS / JS (light + dark mode)
docs/                  architecture, meeting notes, client Q&A
legacy/opspilot/       earlier Next.js prototype, kept for reference
```

## Run it

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 (frontend) or http://localhost:8000/docs (API docs).

Run tests: `cd backend && pytest`

## Workflow

See [CONTRIBUTING.md](CONTRIBUTING.md) for branches, commits and pull requests.

