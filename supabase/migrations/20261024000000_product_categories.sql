-- Product catalogue: add categories and a fuller furniture range so common
-- order lines (mattresses, bed frames, shelves, tables...) validate.

alter table public.products add column if not exists category text not null default 'Other';
create index if not exists products_category_idx on public.products (category);

insert into public.products (sku, name, category, unit_price) values
  -- Sofas
  ('SOFA-AURA-3S', 'Aura 3-seater sofa, bouclé ivory', 'Sofas', 1890.00),
  ('SOFA-AURA-2S', 'Aura 2-seater sofa, bouclé ivory', 'Sofas', 1490.00),
  ('SOFA-LIN-L', 'Haven L-shape sofa, sage linen', 'Sofas', 2690.00),
  ('SOFA-BED-3S', 'Nook 3-seater sofa bed, grey', 'Sofas', 1590.00),
  ('ARM-BOU-IV', 'Aura armchair, bouclé ivory', 'Sofas', 890.00),

  -- Tables
  ('TBL-OAK-180', 'Oslo oak dining table 180cm', 'Tables', 1250.00),
  ('TBL-OAK-140', 'Oslo oak dining table 140cm', 'Tables', 990.00),
  ('TBL-TEAK-220', 'Bali teak dining table 220cm', 'Tables', 2180.00),
  ('TBL-RND-120', 'Luna round dining table 120cm, walnut', 'Tables', 1150.00),
  ('TBL-COF-OAK', 'Oslo oak coffee table 110cm', 'Tables', 520.00),
  ('TBL-SIDE-TK', 'Bali teak side table', 'Tables', 240.00),
  ('TBL-CON-WAL', 'Luna walnut console table 120cm', 'Tables', 680.00),

  -- Chairs
  ('CHR-OAK-DIN', 'Oslo oak dining chair', 'Chairs', 240.00),
  ('CHR-TEAK-DIN', 'Bali teak dining chair, rattan seat', 'Chairs', 290.00),
  ('CHR-BAR-OAK', 'Oslo oak bar stool 75cm', 'Chairs', 210.00),
  ('CHR-OFF-ERG', 'Studio ergonomic office chair', 'Chairs', 460.00),

  -- Bed frames
  ('BED-OAK-S', 'Nord oak bed frame, single', 'Bed frames', 890.00),
  ('BED-OAK-SS', 'Nord oak bed frame, super single', 'Bed frames', 990.00),
  ('BED-OAK-Q', 'Nord oak bed frame, queen', 'Bed frames', 1380.00),
  ('BED-OAK-K', 'Nord oak bed frame, king', 'Bed frames', 1580.00),
  ('BED-TEAK-Q', 'Bali teak bed frame, queen', 'Bed frames', 1790.00),
  ('BED-UPH-Q', 'Haven upholstered bed frame, queen, linen', 'Bed frames', 1290.00),
  ('BED-STO-Q', 'Nook storage bed frame with drawers, queen', 'Bed frames', 1490.00),

  -- Mattresses
  ('MAT-PKT-S', 'Rest pocket-spring mattress, single', 'Mattresses', 590.00),
  ('MAT-PKT-SS', 'Rest pocket-spring mattress, super single', 'Mattresses', 690.00),
  ('MAT-PKT-Q', 'Rest pocket-spring mattress, queen', 'Mattresses', 990.00),
  ('MAT-PKT-K', 'Rest pocket-spring mattress, king', 'Mattresses', 1190.00),
  ('MAT-MEM-Q', 'Cloud memory foam mattress, queen', 'Mattresses', 1290.00),
  ('MAT-MEM-K', 'Cloud memory foam mattress, king', 'Mattresses', 1490.00),
  ('MAT-LTX-Q', 'Pure natural latex mattress, queen', 'Mattresses', 1690.00),
  ('MAT-TOP-Q', 'Cloud mattress topper 5cm, queen', 'Mattresses', 290.00),

  -- Shelving & storage
  ('SHL-OAK-5T', 'Studio oak bookshelf, 5 tier', 'Shelving & storage', 560.00),
  ('SHL-OAK-3T', 'Studio oak bookshelf, 3 tier', 'Shelving & storage', 390.00),
  ('SHL-WAL-WALL', 'Luna walnut wall shelf 90cm', 'Shelving & storage', 120.00),
  ('SHL-TEAK-LAD', 'Bali teak ladder shelf', 'Shelving & storage', 340.00),
  ('SHL-CUBE-9', 'Nook 9-cube storage shelf, oak', 'Shelving & storage', 420.00),
  ('CAB-TEAK-SB', 'Bali teak sideboard 160cm', 'Shelving & storage', 1640.00),
  ('CAB-OAK-TV', 'Oslo oak TV console 180cm', 'Shelving & storage', 890.00),
  ('WRD-OAK-2D', 'Nord oak wardrobe, 2-door', 'Shelving & storage', 1450.00),
  ('WRD-OAK-3D', 'Nord oak wardrobe, 3-door', 'Shelving & storage', 1950.00),
  ('DRW-OAK-6', 'Nord oak chest of 6 drawers', 'Shelving & storage', 980.00),
  ('NST-OAK-2D', 'Nord oak bedside table, 2 drawers', 'Shelving & storage', 260.00),

  -- Desks
  ('DSK-OAK-140', 'Studio oak desk 140cm', 'Desks', 890.00),
  ('DSK-OAK-120', 'Studio oak desk 120cm', 'Desks', 720.00),
  ('DSK-STAND-EL', 'Studio electric standing desk 160cm', 'Desks', 1190.00),

  -- Ottomans & benches
  ('OTT-LIN-SG', 'Linen ottoman, sage', 'Ottomans & benches', 320.00),
  ('BEN-OAK-140', 'Oslo oak dining bench 140cm', 'Ottomans & benches', 380.00),
  ('BEN-UPH-BED', 'Haven upholstered bed-end bench', 'Ottomans & benches', 450.00),

  -- Outdoor
  ('OUT-TEAK-SET4', 'Bali teak outdoor dining set, 4 seats', 'Outdoor', 2490.00),
  ('OUT-TEAK-LNG', 'Bali teak sun lounger', 'Outdoor', 890.00),

  -- Lighting & decor
  ('LMP-BRS-FL', 'Brass floor lamp', 'Lighting & decor', 380.00),
  ('LMP-BRS-TB', 'Brass table lamp', 'Lighting & decor', 180.00),
  ('RUG-WOOL-200', 'Hand-tufted wool rug 200 x 300cm', 'Lighting & decor', 690.00),
  ('MIR-OAK-RND', 'Oak round wall mirror 80cm', 'Lighting & decor', 260.00)
on conflict (sku) do update
  set name = excluded.name,
      category = excluded.category,
      unit_price = excluded.unit_price;
