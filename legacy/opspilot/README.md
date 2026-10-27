# OpsPilot: AI back-office workspace

One web app that combines three project briefs:

| Module | Brief | Where |
| --- | --- | --- |
| **Invoice checking** | Koda (6b): read supplier invoices, compare with POs and existing records, flag mismatches for review | `/invoices` |
| **Order automation** | Spectra (11): extract purchase/sales orders, validate line items, approve and export for ERP | `/orders` |
| **Projects & tasks** | EM Services (12h): projects, task board, owners, deadlines, progress | `/projects` |

The modules are connected. A flagged invoice or an order that fails validation automatically becomes a task on the
**Invoice Exceptions** / **Order Exceptions** board. Approving or fixing the record closes that task. Everything is written to a
shared audit log.

## Stack

- **Next.js 16** (App Router, Server Actions, `src/proxy.ts` for auth)
- **Supabase**: Auth, Postgres (RLS on), Storage (private `documents` bucket), Realtime (task board)
- **OpenAI** (Responses API + Zod structured outputs) for document extraction and task suggestions

## Setup

1. Create a free project at [supabase.com](https://supabase.com).
2. Push the database (tables, RLS, storage bucket, realtime + demo data) with the Supabase CLI:
   ```bash
   npx supabase login
   npx supabase link --project-ref <your-project-ref>
   npx supabase db push --include-seed
   ```
   The schema lives in `supabase/migrations/`, demo data in `supabase/seed.sql`.
   (Alternative: paste both files into the Supabase SQL editor, migration first.)
3. For quick demos, turn off **Authentication → Providers → Email → Confirm email**.
4. Create `.env.local` with the Supabase URL and anon/publishable key (see `.env.example`).
   - Add `OPENAI_API_KEY` to use real AI extraction (`OPENAI_MODEL` optional, default `gpt-5.4-mini`).
   - Leave it empty for **demo mode**. Uploads then produce realistic mock extractions built from the seeded POs (sometimes clean, sometimes with a price or quantity mismatch).
5. `npm install` then `npm run dev`, and open http://localhost:3000.
6. Sign up. The **first account becomes admin**. Later sign-ups are staff, and you can promote them on `/team`.

## CRUD by module

| | Create | Read | Update | Delete |
| --- | --- | --- | --- | --- |
| Invoices | upload (AI) or enter manually | review queue, compare page | edit fields/lines → re-check vs PO; approve/reject; reopen | reviewer/admin |
| Orders | upload (AI) or enter manually | tabs by status | edit fields/lines → re-validate; approve; reopen | reviewer/admin |
| Projects | new project form | cards with progress | name, brief, due date, status | deletes its tasks too |
| Tasks | add form or AI suggestions | board + filters | drag between columns, title, details, owner, priority, due | from the task card |

## Roles

| Role | Can |
| --- | --- |
| staff | upload documents, correct extracted orders, manage projects/tasks |
| reviewer | + approve/reject invoices, approve orders for export |
| admin | + change roles |

## Where the logic lives

- `src/lib/ai.ts`: OpenAI extraction (invoice, order) and the task planner, plus demo-mode mocks
- `src/lib/matching.ts`: invoice ↔ PO rules (duplicate, supplier, line not on PO, price drift > 1%, over-billed qty, arithmetic, low confidence)
- `src/lib/orders.ts`: order validation (missing fields, unknown SKU, price deviation > 10% from catalogue, totals) and CSV export
- `src/lib/workflow.ts`: audit log, storage helpers, auto-created exception tasks
- `supabase/migrations/`: tables, RLS, storage bucket, realtime
