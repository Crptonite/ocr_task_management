-- Run once in the Supabase SQL editor (Dashboard > SQL Editor).
-- The backend uses the service-role key, which bypasses RLS; RLS stays on with no policies
-- so the table is closed to the public anon key.

create table if not exists public.koda_invoices (
  id uuid primary key default gen_random_uuid(),
  invoice_number text not null,
  po_number text,
  supplier text,
  invoice_date date,
  currency text,
  tax_rate numeric,
  tax_amount numeric,
  lines jsonb not null default '[]',
  source_file text,
  file_path text,
  created_at timestamptz not null default now()
);
create index if not exists koda_invoices_number_idx on public.koda_invoices (invoice_number);
alter table public.koda_invoices enable row level security;

-- Private bucket for uploaded documents (no-op if the legacy app already created it).
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;
