import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { requireUser } from "@/lib/supabase/server";
import { PageHeader } from "@/components/ui";
import { InvoiceGenerator, type PoOption } from "./invoice-generator";

export default async function InvoiceGeneratorPage() {
  const { supabase } = await requireUser();
  const { data } = await supabase
    .from("purchase_orders")
    .select("po_number, currency, suppliers(name, email), po_lines(sku, description, quantity, unit_price)")
    .order("po_number");

  const pos: PoOption[] = (data ?? []).map((po) => {
    const supplier = po.suppliers as unknown as { name: string; email: string | null } | null;
    return {
      po_number: po.po_number,
      currency: po.currency,
      supplier_name: supplier?.name ?? "",
      supplier_email: supplier?.email ?? "",
      lines: po.po_lines.map((l) => ({
        sku: l.sku ?? "",
        description: l.description,
        quantity: Number(l.quantity),
        unit_price: Number(l.unit_price),
      })),
    };
  });

  return (
    <>
      <Link href="/invoices" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Invoices
      </Link>
      <PageHeader
        title="Invoice generator"
        description="Create a supplier invoice as a PDF. Start from a purchase order, add a deliberate mismatch if you like, then download it or send it straight to the invoice checker."
      />
      <InvoiceGenerator pos={pos} />
    </>
  );
}
