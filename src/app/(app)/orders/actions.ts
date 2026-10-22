"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { canReview, requireUser } from "@/lib/supabase/server";
import { aiEnabled, extractOrder } from "@/lib/ai";
import { validateOrder, type CatalogItem, type OrderHeaderInput, type OrderLineInput } from "@/lib/orders";
import {
  audit,
  closeExceptionTasks,
  deleteExceptionTasks,
  downloadDocument,
  openExceptionTask,
  removeDocument,
  syncExceptionTask,
} from "@/lib/workflow";
import type { SupabaseClient } from "@supabase/supabase-js";

async function loadCatalog(supabase: SupabaseClient): Promise<CatalogItem[]> {
  const { data } = await supabase.from("products").select("sku, name, unit_price").eq("active", true);
  return (data ?? []).map((p) => ({ ...p, unit_price: Number(p.unit_price) }));
}

export async function processOrder(path: string, mediaType: string, fileName: string) {
  const { supabase, profile } = await requireUser();
  try {
    const data = await downloadDocument(supabase, path);
    const ex = await extractOrder({ data, mediaType });
    const { issues, lineIssues, status } = validateOrder(ex, ex.lines, await loadCatalog(supabase));

    const { data: order, error } = await supabase
      .from("orders")
      .insert({
        order_type: ex.order_type,
        order_number: ex.order_number,
        counterparty: ex.counterparty,
        order_date: ex.order_date,
        delivery_date: ex.delivery_date,
        currency: ex.currency ?? "SGD",
        total: ex.total,
        status,
        issues,
        file_path: path,
        file_name: fileName,
        extracted: ex,
        uploaded_by: profile.id,
      })
      .select("id")
      .single();
    if (error || !order) throw new Error(error?.message ?? "Could not save order");

    if (ex.lines.length) {
      await supabase
        .from("order_lines")
        .insert(ex.lines.map((l, i) => ({ ...l, order_id: order.id, line_no: i + 1, issues: lineIssues[i] })));
    }

    await audit(supabase, profile.id, "order", order.id, "uploaded", {
      file: fileName,
      status,
      issues: issues.length,
      mode: aiEnabled ? "openai" : "demo",
    });

    if (status === "needs_attention") {
      await openExceptionTask(
        supabase,
        profile.id,
        "order",
        order.id,
        `Fix order ${ex.order_number ?? fileName} (${ex.counterparty ?? "unknown party"})`,
        issues.map((i) => `• ${i}`).join("\n"),
        "medium",
      );
    }

    revalidatePath("/orders");
    revalidatePath("/");
    return { id: order.id as string };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Processing failed" };
  }
}

/** Saves human corrections, then re-runs validation. */
export async function saveOrder(
  id: string,
  header: OrderHeaderInput & { currency: string | null; order_type: "purchase" | "sales" },
  lines: OrderLineInput[],
) {
  const { supabase, profile } = await requireUser();
  const { data: existing } = await supabase.from("orders").select("status").eq("id", id).single();
  if (!existing || existing.status === "approved" || existing.status === "exported") {
    return { error: "Approved orders can no longer be edited." };
  }

  const clean = lines
    .filter((l) => l.description.trim())
    .map((l) => ({ ...l, sku: l.sku?.trim() || null, amount: Math.round(l.quantity * l.unit_price * 100) / 100 }));
  const { issues, lineIssues, status } = validateOrder(header, clean, await loadCatalog(supabase));

  await supabase
    .from("orders")
    .update({
      order_type: header.order_type === "sales" ? "sales" : "purchase",
      order_number: header.order_number || null,
      counterparty: header.counterparty || null,
      order_date: header.order_date || null,
      delivery_date: header.delivery_date || null,
      currency: header.currency || "SGD",
      total: header.total,
      status,
      issues,
    })
    .eq("id", id);
  await supabase.from("order_lines").delete().eq("order_id", id);
  if (clean.length) {
    await supabase
      .from("order_lines")
      .insert(clean.map((l, i) => ({ ...l, order_id: id, line_no: i + 1, issues: lineIssues[i] })));
  }
  await syncExceptionTask(
    supabase,
    profile.id,
    "order",
    id,
    status === "needs_attention",
    `Fix order ${header.order_number ?? "order"} (${header.counterparty ?? "unknown party"})`,
    issues.map((i) => `• ${i}`).join("\n"),
    "medium",
  );
  await audit(supabase, profile.id, "order", id, "edited", { status, issues: issues.length });

  revalidatePath(`/orders/${id}`);
  revalidatePath("/orders");
  return { status, issues, lineIssues };
}

export async function approveOrder(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can approve orders.");
  const id = String(formData.get("id"));

  const { data: order } = await supabase.from("orders").select("status").eq("id", id).single();
  if (order?.status !== "ready") throw new Error("Only orders that pass validation can be approved.");

  await supabase
    .from("orders")
    .update({ status: "approved", approved_by: profile.id, approved_at: new Date().toISOString() })
    .eq("id", id);
  await closeExceptionTasks(supabase, "order", id);
  await audit(supabase, profile.id, "order", id, "approved");

  revalidatePath(`/orders/${id}`);
  revalidatePath("/orders");
  revalidatePath("/");
}

/** Creates an empty order for manual keying (no document). */
export async function createManualOrder() {
  const { supabase, profile } = await requireUser();
  const { data, error } = await supabase
    .from("orders")
    .insert({
      order_type: "sales",
      currency: "SGD",
      status: "needs_attention",
      issues: ["Missing order number", "Missing customer / supplier", "Missing order date", "No line items found"],
      file_name: "Manual entry",
      uploaded_by: profile.id,
    })
    .select("id")
    .single();
  if (error || !data) throw new Error(error?.message ?? "Could not create order");
  await audit(supabase, profile.id, "order", data.id, "created manually");
  redirect(`/orders/${data.id}`);
}

/** Moves an approved (not yet exported) order back to editing. */
export async function reopenOrder(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can reopen orders.");
  const id = String(formData.get("id"));
  const { data: order } = await supabase.from("orders").select("status").eq("id", id).single();
  if (order?.status !== "approved") throw new Error("Only approved, unexported orders can be reopened.");
  await supabase.from("orders").update({ status: "ready", approved_by: null, approved_at: null }).eq("id", id);
  await audit(supabase, profile.id, "order", id, "reopened");
  revalidatePath(`/orders/${id}`);
  revalidatePath("/orders");
}

export async function deleteOrder(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can delete orders.");
  const id = String(formData.get("id"));

  const { data: order } = await supabase.from("orders").select("order_number, file_path").eq("id", id).single();
  await deleteExceptionTasks(supabase, "order", id);
  const { error } = await supabase.from("orders").delete().eq("id", id);
  if (error) throw new Error(error.message);
  await removeDocument(supabase, order?.file_path ?? null);
  await audit(supabase, profile.id, "order", id, "deleted", { order_number: order?.order_number ?? null });

  revalidatePath("/orders");
  revalidatePath("/");
  redirect("/orders");
}
