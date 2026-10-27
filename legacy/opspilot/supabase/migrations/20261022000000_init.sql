-- OpsPilot schema: invoice checking + order automation + project tracker
-- Run this once in the Supabase SQL editor, then run seed.sql.

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Users / roles
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  email text,
  role text not null default 'staff' check (role in ('admin', 'reviewer', 'staff')),
  created_at timestamptz not null default now()
);

-- First user to sign up becomes admin, everyone after is staff.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, email, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1)),
    new.email,
    case when exists (select 1 from public.profiles) then 'staff' else 'admin' end
  );
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Reference data: suppliers, purchase orders, product catalogue
-- ---------------------------------------------------------------------------
create table if not exists public.suppliers (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  email text,
  created_at timestamptz not null default now()
);

create table if not exists public.purchase_orders (
  id uuid primary key default gen_random_uuid(),
  po_number text not null unique,
  supplier_id uuid references public.suppliers (id),
  order_date date,
  currency text not null default 'SGD',
  total numeric(12, 2) not null default 0,
  status text not null default 'open' check (status in ('open', 'closed')),
  created_at timestamptz not null default now()
);

create table if not exists public.po_lines (
  id uuid primary key default gen_random_uuid(),
  po_id uuid not null references public.purchase_orders (id) on delete cascade,
  sku text,
  description text not null,
  quantity numeric(12, 2) not null,
  unit_price numeric(12, 2) not null
);

create table if not exists public.products (
  sku text primary key,
  name text not null,
  unit_price numeric(12, 2) not null,
  active boolean not null default true
);

-- ---------------------------------------------------------------------------
-- Module 1: invoice checking
-- ---------------------------------------------------------------------------
create table if not exists public.invoices (
  id uuid primary key default gen_random_uuid(),
  invoice_number text,
  supplier_name text,
  supplier_id uuid references public.suppliers (id),
  po_number text,
  po_id uuid references public.purchase_orders (id),
  invoice_date date,
  due_date date,
  currency text,
  subtotal numeric(12, 2),
  tax numeric(12, 2),
  total numeric(12, 2),
  confidence numeric(4, 2),
  status text not null default 'flagged'
    check (status in ('matched', 'flagged', 'approved', 'rejected')),
  file_path text,
  file_name text,
  extracted jsonb,
  uploaded_by uuid references public.profiles (id),
  reviewed_by uuid references public.profiles (id),
  reviewed_at timestamptz,
  review_note text,
  created_at timestamptz not null default now()
);

create table if not exists public.invoice_lines (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices (id) on delete cascade,
  sku text,
  description text not null,
  quantity numeric(12, 2) not null,
  unit_price numeric(12, 2) not null,
  amount numeric(12, 2) not null
);

create table if not exists public.invoice_flags (
  id uuid primary key default gen_random_uuid(),
  invoice_id uuid not null references public.invoices (id) on delete cascade,
  code text not null,
  severity text not null check (severity in ('high', 'medium', 'low')),
  message text not null,
  expected text,
  actual text,
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Module 2: order automation
-- ---------------------------------------------------------------------------
create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  order_type text not null default 'purchase' check (order_type in ('purchase', 'sales')),
  order_number text,
  counterparty text,
  order_date date,
  delivery_date date,
  currency text,
  total numeric(12, 2),
  status text not null default 'needs_attention'
    check (status in ('needs_attention', 'ready', 'approved', 'exported')),
  issues text[] not null default '{}',
  file_path text,
  file_name text,
  extracted jsonb,
  uploaded_by uuid references public.profiles (id),
  approved_by uuid references public.profiles (id),
  approved_at timestamptz,
  exported_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.order_lines (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  line_no int not null,
  sku text,
  description text not null,
  quantity numeric(12, 2) not null,
  unit_price numeric(12, 2) not null,
  amount numeric(12, 2) not null,
  issues text[] not null default '{}'
);

-- ---------------------------------------------------------------------------
-- Module 3: project tracker
-- ---------------------------------------------------------------------------
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  status text not null default 'active' check (status in ('planning', 'active', 'on_hold', 'done')),
  owner_id uuid references public.profiles (id),
  due_date date,
  created_at timestamptz not null default now()
);

create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects (id) on delete cascade,
  title text not null,
  description text,
  status text not null default 'todo' check (status in ('todo', 'in_progress', 'review', 'done')),
  priority text not null default 'medium' check (priority in ('low', 'medium', 'high')),
  assignee_id uuid references public.profiles (id),
  due_date date,
  source_type text check (source_type in ('invoice', 'order')),
  source_id uuid,
  created_by uuid references public.profiles (id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Shared audit log
-- ---------------------------------------------------------------------------
create table if not exists public.audit_logs (
  id bigint generated always as identity primary key,
  actor_id uuid references public.profiles (id),
  entity_type text not null,
  entity_id uuid,
  action text not null,
  details jsonb,
  created_at timestamptz not null default now()
);

create index if not exists invoices_status_idx on public.invoices (status);
create index if not exists orders_status_idx on public.orders (status);
create index if not exists tasks_project_idx on public.tasks (project_id);
create index if not exists audit_created_idx on public.audit_logs (created_at desc);

-- ---------------------------------------------------------------------------
-- Row level security: any signed-in user can work with business data.
-- Approve / reject / role changes are additionally checked in the app.
-- ---------------------------------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array[
    'suppliers', 'purchase_orders', 'po_lines', 'products',
    'invoices', 'invoice_lines', 'invoice_flags',
    'orders', 'order_lines', 'projects', 'tasks', 'audit_logs'
  ]
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "authenticated full access" on public.%I', t);
    execute format(
      'create policy "authenticated full access" on public.%I for all to authenticated using (true) with check (true)', t
    );
  end loop;
end $$;

alter table public.profiles enable row level security;
drop policy if exists "profiles readable" on public.profiles;
create policy "profiles readable" on public.profiles for select to authenticated using (true);
drop policy if exists "update own profile" on public.profiles;
create policy "update own profile" on public.profiles for update to authenticated
  using (id = auth.uid())
  with check (id = auth.uid() and role = (select p.role from public.profiles p where p.id = auth.uid()));
drop policy if exists "admins manage profiles" on public.profiles;
create policy "admins manage profiles" on public.profiles for update to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

-- ---------------------------------------------------------------------------
-- Realtime for the task board
-- ---------------------------------------------------------------------------
do $$
begin
  alter publication supabase_realtime add table public.tasks;
exception when duplicate_object then null;
end $$;

-- ---------------------------------------------------------------------------
-- Private storage bucket for uploaded documents
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('documents', 'documents', false)
on conflict (id) do nothing;

drop policy if exists "documents read" on storage.objects;
create policy "documents read" on storage.objects for select to authenticated
  using (bucket_id = 'documents');
drop policy if exists "documents upload" on storage.objects;
create policy "documents upload" on storage.objects for insert to authenticated
  with check (bucket_id = 'documents');
drop policy if exists "documents delete" on storage.objects;
create policy "documents delete" on storage.objects for delete to authenticated
  using (bucket_id = 'documents');
