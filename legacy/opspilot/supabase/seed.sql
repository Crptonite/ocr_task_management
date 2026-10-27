-- Demo data: suppliers, open purchase orders, product catalogue, starter projects.
-- Safe to re-run.

insert into public.suppliers (name, email) values
  ('Teak & Timber Supplies Pte Ltd', 'billing@teaktimber.sg'),
  ('Hafele Hardware Asia', 'ar@hafele-asia.com'),
  ('Lumina Fabrics Co', 'accounts@luminafabrics.com'),
  ('Nordic Foam Industries', 'invoices@nordicfoam.com')
on conflict (name) do nothing;

insert into public.purchase_orders (po_number, supplier_id, order_date, currency, total)
select v.po_number, s.id, v.order_date::date, 'SGD', v.total
from (values
  ('PO-2026-0141', 'Teak & Timber Supplies Pte Ltd', '2026-09-28', 13300.00),
  ('PO-2026-0142', 'Hafele Hardware Asia', '2026-10-01', 2965.00),
  ('PO-2026-0143', 'Lumina Fabrics Co', '2026-10-03', 5080.00),
  ('PO-2026-0144', 'Nordic Foam Industries', '2026-10-06', 3720.00)
) as v(po_number, supplier, order_date, total)
join public.suppliers s on s.name = v.supplier
on conflict (po_number) do nothing;

insert into public.po_lines (po_id, sku, description, quantity, unit_price)
select po.id, v.sku, v.description, v.quantity, v.unit_price
from (values
  ('PO-2026-0141', 'TK-PLK-2440', 'Teak plank 2440 x 200 x 25mm', 200, 48.50),
  ('PO-2026-0141', 'OK-PLK-2440', 'White oak plank 2440 x 200 x 25mm', 100, 36.00),
  ('PO-2026-0142', 'HF-HNG-110', 'Soft-close concealed hinge 110°', 500, 3.20),
  ('PO-2026-0142', 'HF-SLD-450', 'Full-extension drawer slide 450mm', 150, 8.50),
  ('PO-2026-0142', 'HF-KNB-032', 'Brushed brass cabinet knob 32mm', 200, 0.45),
  ('PO-2026-0143', 'LF-BOU-140', 'Bouclé upholstery fabric, ivory (m)', 120, 28.00),
  ('PO-2026-0143', 'LF-LIN-140', 'Washed linen fabric, sage (m)', 80, 21.50),
  ('PO-2026-0144', 'NF-HD-50', 'High-density foam sheet 50mm', 60, 42.00),
  ('PO-2026-0144', 'NF-MEM-25', 'Memory foam topper sheet 25mm', 40, 30.00)
) as v(po_number, sku, description, quantity, unit_price)
join public.purchase_orders po on po.po_number = v.po_number
where not exists (select 1 from public.po_lines l where l.po_id = po.id);

insert into public.products (sku, name, unit_price) values
  ('SOFA-AURA-3S', 'Aura 3-seater sofa, bouclé ivory', 1890.00),
  ('SOFA-AURA-2S', 'Aura 2-seater sofa, bouclé ivory', 1490.00),
  ('TBL-OAK-180', 'Oslo oak dining table 180cm', 1250.00),
  ('TBL-TEAK-220', 'Bali teak dining table 220cm', 2180.00),
  ('CHR-OAK-DIN', 'Oslo oak dining chair', 240.00),
  ('CAB-TEAK-SB', 'Bali teak sideboard 160cm', 1640.00),
  ('BED-OAK-Q', 'Nord oak bed frame, queen', 1380.00),
  ('DSK-OAK-140', 'Studio oak desk 140cm', 890.00),
  ('SHL-OAK-5T', 'Studio oak bookshelf, 5 tier', 560.00),
  ('OTT-LIN-SG', 'Linen ottoman, sage', 320.00)
on conflict (sku) do nothing;

insert into public.projects (name, description, status, due_date)
select * from (values
  ('Invoice Exceptions', 'Auto-created tasks for supplier invoices that failed AI checks.', 'active', null::date),
  ('Order Exceptions', 'Auto-created tasks for extracted orders that need a human fix.', 'active', null::date),
  ('Showroom Refit – Tampines', 'Refit the Tampines showroom with the autumn collection.', 'active', '2026-11-30'::date)
) as v(name, description, status, due_date)
where not exists (select 1 from public.projects p where p.name = v.name);

insert into public.tasks (project_id, title, status, priority, due_date)
select p.id, v.title, v.status, v.priority, v.due_date::date
from (values
  ('Measure floor plan and lighting points', 'done', 'medium', '2026-10-10'),
  ('Order display stock for autumn collection', 'in_progress', 'high', '2026-10-24'),
  ('Book contractor for flooring', 'todo', 'high', '2026-10-20'),
  ('Design window signage', 'review', 'low', '2026-11-05'),
  ('Plan launch weekend promotion', 'todo', 'medium', '2026-11-20')
) as v(title, status, priority, due_date)
join public.projects p on p.name = 'Showroom Refit – Tampines'
where not exists (select 1 from public.tasks t where t.project_id = p.id);
