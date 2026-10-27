"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/supabase/server";
import { audit } from "@/lib/workflow";

export type NewPoInput = {
  po_number: string;
  supplier_name: string;
  order_date: string | null;
  currency: string;
  lines: { sku: string | null; description: string; quantity: number; unit_price: number }[];
};

export async function createPurchaseOrder(input: NewPoInput) {
  const { supabase, profile } = await requireUser();

  const poNumber = input.po_number.trim().toUpperCase();
  const supplierName = input.supplier_name.trim();
  const lines = input.lines
    .filter((l) => l.description.trim())
    .map((l) => ({
      sku: l.sku?.trim() || null,
      description: l.description.trim(),
      quantity: l.quantity,
      unit_price: l.unit_price,
    }));
  if (!poNumber) return { error: "PO number is required." };
  if (!supplierName) return { error: "Supplier is required." };
  if (lines.length === 0) return { error: "Add at least one line item." };
  if (lines.some((l) => l.quantity <= 0 || l.unit_price < 0)) {
    return { error: "Quantities must be positive and prices cannot be negative." };
  }

  const { data: existing } = await supabase.from("purchase_orders").select("id").ilike("po_number", poNumber).maybeSingle();
  if (existing) return { error: `${poNumber} already exists.` };

  // Reuse the supplier if it exists (case-insensitive), otherwise create it.
  let { data: supplier } = await supabase.from("suppliers").select("id").ilike("name", supplierName).maybeSingle();
  if (!supplier) {
    const created = await supabase.from("suppliers").insert({ name: supplierName }).select("id").single();
    if (created.error) return { error: created.error.message };
    supplier = created.data;
  }

  const total = Math.round(lines.reduce((s, l) => s + l.quantity * l.unit_price, 0) * 100) / 100;
  const { data: po, error } = await supabase
    .from("purchase_orders")
    .insert({
      po_number: poNumber,
      supplier_id: supplier.id,
      order_date: input.order_date || null,
      currency: input.currency.trim().toUpperCase() || "SGD",
      total,
    })
    .select("id")
    .single();
  if (error || !po) return { error: error?.message ?? "Could not create purchase order." };

  const { error: linesError } = await supabase.from("po_lines").insert(lines.map((l) => ({ ...l, po_id: po.id })));
  if (linesError) {
    await supabase.from("purchase_orders").delete().eq("id", po.id);
    return { error: linesError.message };
  }

  await audit(supabase, profile.id, "purchase_order", po.id, "created", { po_number: poNumber, total });
  revalidatePath("/purchase-orders");
  return { id: po.id as string };
}

export async function deletePurchaseOrder(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const id = String(formData.get("id"));

  const { data: po } = await supabase.from("purchase_orders").select("po_number").eq("id", id).single();
  // Invoices keep their PO number text; only the link is cleared so the delete is allowed.
  await supabase.from("invoices").update({ po_id: null }).eq("po_id", id);
  const { error } = await supabase.from("purchase_orders").delete().eq("id", id);
  if (error) throw new Error(error.message);

  await audit(supabase, profile.id, "purchase_order", id, "deleted", { po_number: po?.po_number ?? null });
  revalidatePath("/purchase-orders");
  revalidatePath("/invoices");
}
