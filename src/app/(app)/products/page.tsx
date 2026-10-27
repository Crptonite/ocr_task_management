import { requireUser } from "@/lib/supabase/server";
import { PageHeader } from "@/components/ui";
import { Catalogue, type Product } from "./catalogue";

export default async function ProductsPage() {
  const { supabase } = await requireUser();
  const { data } = await supabase
    .from("products")
    .select("sku, name, category, unit_price, active")
    .order("category")
    .order("name");

  const products: Product[] = (data ?? []).map((p) => ({ ...p, unit_price: Number(p.unit_price) }));

  return (
    <>
      <PageHeader
        title="Product catalogue"
        description="SKUs and list prices that extracted orders are validated against. Lines with a SKU missing here are flagged “SKU not in catalogue”."
      />
      <Catalogue products={products} />
    </>
  );
}
