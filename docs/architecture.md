# Architecture (draft)

```
Invoice PDF / scan
      │
      ▼
Extraction (backend/app/ai)          OCR / LLM → structured JSON        [Lucas]
      │
      ▼
Matching (backend/app/services)      invoice vs PO (later + GRN)        [Aeric]
      │
      ▼
Review UI (frontend)                 staff check flags, approve / edit  [Qizhi]
      │
      ▼
Export                               CSV / Excel for Dynamics           [Aeric]

Tests across all layers                                                [Wesley]
```

## API (v0.2)

The app is one workspace for three problem statements. Each has its own router in `backend/app/routers/` and a tab in the frontend.
Data is mock JSON in `backend/app/data/`, held in memory by `app/store.py` (edits reset on restart) until SQLAlchemy + Supabase replace it.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| **Koda: invoices** | | |
| GET | `/api/invoices` | Invoices with match result |
| GET | `/api/invoices/{number}` | One invoice |
| GET | `/api/purchase-orders` | Mock ERP purchase orders |
| POST | `/api/invoices/upload` | Upload file → extract; if every field is read, add to review queue |
| GET | `/api/invoice-variants` | Test invoice variants (clean, price, qty, tax) |
| GET | `/api/purchase-orders/{po}/invoice.pdf?variant=` | Generate a supplier invoice PDF from a PO |
| **Spectra: orders** | | |
| GET | `/api/catalog` | Product catalogue used for validation |
| GET | `/api/orders` | Extracted orders with validation result |
| GET | `/api/orders/{id}` | One order |
| POST | `/api/orders/{id}/approve` | Approve a valid order (409 if it has issues) |
| GET | `/api/orders/export.csv` | Approved orders as CSV, then marked exported |
| POST | `/api/orders/upload` | Upload file → extraction draft |
| **EM Services: projects** | | |
| GET | `/api/members` | Staff who can own tasks |
| GET | `/api/projects` | Projects with progress, overdue count, health |
| GET | `/api/projects/{id}` | Project with its tasks |
| POST | `/api/projects/{id}/tasks` | Create task |
| PATCH | `/api/tasks/{id}` | Update title / owner / deadline / status |
| DELETE | `/api/tasks/{id}` | Delete task |
| GET | `/api/projects/{id}/overdue-summary` | AI summary of overdue work |
| POST | `/api/projects/{id}/suggest-tasks` | AI task suggestions from the brief |

Project endpoints accept `?today=YYYY-MM-DD` to pin the date for demos and tests.

## Open questions (after client meeting)

- 2-way or 3-way matching?
- Tolerance thresholds for price / tax?
- Dynamics version and import format?

