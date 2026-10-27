-- Users who signed up before the schema existed have no profiles row, which
-- breaks every foreign key to profiles (e.g. invoices.uploaded_by).

-- 1. Backfill: create a profile for every auth user that lacks one.
--    If there is no admin yet, the earliest user becomes admin.
insert into public.profiles (id, full_name, email, role)
select
  u.id,
  coalesce(u.raw_user_meta_data ->> 'full_name', split_part(u.email, '@', 1)),
  u.email,
  case
    when not exists (select 1 from public.profiles where role = 'admin')
     and u.id = (select id from auth.users order by created_at limit 1)
    then 'admin'
    else 'staff'
  end
from auth.users u
where not exists (select 1 from public.profiles p where p.id = u.id);

-- 2. Self-heal: the app calls this when the signed-in user has no profile.
create or replace function public.ensure_profile()
returns void
language plpgsql
security definer set search_path = public
as $$
declare
  u auth.users%rowtype;
begin
  if auth.uid() is null then
    return;
  end if;
  select * into u from auth.users where id = auth.uid();
  insert into public.profiles (id, full_name, email, role)
  values (
    u.id,
    coalesce(u.raw_user_meta_data ->> 'full_name', split_part(u.email, '@', 1)),
    u.email,
    case when exists (select 1 from public.profiles) then 'staff' else 'admin' end
  )
  on conflict (id) do nothing;
end;
$$;

revoke all on function public.ensure_profile() from public, anon;
grant execute on function public.ensure_profile() to authenticated;
