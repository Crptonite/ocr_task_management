"use server";

import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/supabase/server";
import { audit } from "@/lib/workflow";

function readProduct(formData: FormData) {
  return {
    sku: String(formData.get("sku") ?? "").trim().toUpperCase(),
    name: String(formData.get("name") ?? "").trim(),
    category: String(formData.get("category") ?? "").trim() || "Other",
    unit_price: Number(formData.get("unit_price") ?? 0),
  };
}

export async function createProduct(_prev: { error?: string; ok?: boolean } | null, formData: FormData) {
  const { supabase, profile } = await requireUser();
  const p = readProduct(formData);
  if (!p.sku || !p.name) return { error: "SKU and name are required." };
  if (!(p.unit_price >= 0)) return { error: "Price must be zero or more." };

  const { error } = await supabase.from("products").insert(p);
  if (error) return { error: error.code === "23505" ? `${p.sku} already exists.` : error.message };

  await audit(supabase, profile.id, "product", null, "created", p);
  revalidatePath("/products");
  return { ok: true };
}

/** Adds a product straight from an order line that wasn't in the catalogue. */
export async function addProductFromOrder(input: { sku: string; name: string; category: string; unit_price: number }) {
  const { supabase, profile } = await requireUser();
  const p = {
    sku: input.sku.trim().toUpperCase(),
    name: input.name.trim(),
    category: input.category.trim() || "Other",
    unit_price: Math.max(0, Math.round(input.unit_price * 100) / 100),
  };
  if (!p.sku || !p.name) return { error: "The line needs a SKU and a description first." };

  const { error } = await supabase.from("products").upsert({ ...p, active: true }, { onConflict: "sku" });
  if (error) return { error: error.message };

  await audit(supabase, profile.id, "product", null, "added from order", p);
  revalidatePath("/products");
  return {};
}

export async function updateProduct(sku: string, patch: { name?: string; category?: string; unit_price?: number; active?: boolean }) {
  const { supabase, profile } = await requireUser();
  const { error } = await supabase.from("products").update(patch).eq("sku", sku);
  if (error) return { error: error.message };
  await audit(supabase, profile.id, "product", null, "updated", { sku, ...patch });
  revalidatePath("/products");
  return {};
}

export async function deleteProduct(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const sku = String(formData.get("sku"));
  await supabase.from("products").delete().eq("sku", sku);
  await audit(supabase, profile.id, "product", null, "deleted", { sku });
  revalidatePath("/products");
}
