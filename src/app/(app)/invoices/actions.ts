"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import type { SupabaseClient } from "@supabase/supabase-js";
import { canReview, requireUser } from "@/lib/supabase/server";
import { aiEnabled, extractInvoice, type DemoPo } from "@/lib/ai";
import { compareInvoice, statusFromFlags, type Flag, type InvoiceForMatch } from "@/lib/matching";
import {
  audit,
  closeExceptionTasks,
  deleteExceptionTasks,
  downloadDocument,
  openExceptionTask,
  removeDocument,
  syncExceptionTask,
} from "@/lib/workflow";

export type InvoiceHeaderInput = {
  invoice_number: string | null;
  supplier_name: string | null;
  po_number: string | null;
  invoice_date: string | null;
  due_date: string | null;
  currency: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
};
export type InvoiceLineInput = {
  sku: string | null;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
};

/** Finds the referenced PO, checks for duplicates, and runs every matching rule. */
async function runChecks(supabase: SupabaseClient, inv: InvoiceForMatch, excludeId?: string) {
  const { data: po } = inv.po_number
    ? await supabase
        .from("purchase_orders")
        .select("id, po_number, supplier_id, suppliers(name), po_lines(sku, description, quantity, unit_price)")
        .ilike("po_number", inv.po_number.trim())
        .maybeSingle()
    : { data: null };

  let isDuplicate = false;
  if (inv.invoice_number) {
    let q = supabase
      .from("invoices")
      .select("id", { count: "exact", head: true })
      .eq("invoice_number", inv.invoice_number)
      .ilike("supplier_name", inv.supplier_name ?? "")
      .neq("status", "rejected");
    if (excludeId) q = q.neq("id", excludeId);
    const { count } = await q;
    isDuplicate = (count ?? 0) > 0;
  }

  const flags = compareInvoice(
    inv,
    po
      ? {
          po_number: po.po_number,
          supplier_name: (po.suppliers as unknown as { name: string } | null)?.name ?? null,
          lines: po.po_lines.map((l) => ({ ...l, quantity: Number(l.quantity), unit_price: Number(l.unit_price) })),
        }
      : null,
    isDuplicate,
  );
  return { po, flags, status: statusFromFlags(flags) };
}

async function openTaskIfFlagged(
  supabase: SupabaseClient,
  actorId: string,
  invoiceId: string,
  label: string,
  supplier: string | null,
  flags: Flag[],
) {
  const serious = flags.filter((f) => f.severity !== "low");
  await openExceptionTask(
    supabase,
    actorId,
    "invoice",
    invoiceId,
    `Review invoice ${label} (${supplier ?? "unknown supplier"})`,
    serious.map((f) => `• ${f.message}`).join("\n"),
    flags.some((f) => f.severity === "high") ? "high" : "medium",
  );
}

// ---------------------------------------------------------------------------
// Create
// ---------------------------------------------------------------------------
export async function processInvoice(path: string, mediaType: string, fileName: string) {
  const { supabase, profile } = await requireUser();
  try {
    const data = await downloadDocument(supabase, path);

    let demoPo: DemoPo | null = null;
    if (!aiEnabled) {
      const { data: pos } = await supabase
        .from("purchase_orders")
        .select("po_number, suppliers(name), po_lines(sku, description, quantity, unit_price)")
        .eq("status", "open");
      const po = pos?.[Math.floor(Math.random() * (pos?.length ?? 1))];
      if (po) {
        demoPo = {
          po_number: po.po_number,
          supplier: (po.suppliers as unknown as { name: string } | null)?.name ?? "Supplier",
          lines: po.po_lines.map((l) => ({ ...l, quantity: Number(l.quantity), unit_price: Number(l.unit_price) })),
        };
      }
    }

    const ex = await extractInvoice({ data, mediaType }, demoPo);
    const { po, flags, status } = await runChecks(supabase, ex);

    const { data: invoice, error } = await supabase
      .from("invoices")
      .insert({
        invoice_number: ex.invoice_number,
        supplier_name: ex.supplier_name,
        supplier_id: po?.supplier_id ?? null,
        po_number: ex.po_number,
        po_id: po?.id ?? null,
        invoice_date: ex.invoice_date,
        due_date: ex.due_date,
        currency: ex.currency ?? "SGD",
        subtotal: ex.subtotal,
        tax: ex.tax,
        total: ex.total,
        confidence: ex.confidence,
        status,
        file_path: path,
        file_name: fileName,
        extracted: ex,
        uploaded_by: profile.id,
      })
      .select("id")
      .single();
    if (error || !invoice) throw new Error(error?.message ?? "Could not save invoice");

    if (ex.lines.length) {
      await supabase.from("invoice_lines").insert(ex.lines.map((l) => ({ ...l, invoice_id: invoice.id })));
    }
    if (flags.length) {
      await supabase.from("invoice_flags").insert(flags.map((f) => ({ ...f, invoice_id: invoice.id })));
    }

    await audit(supabase, profile.id, "invoice", invoice.id, "uploaded", {
      file: fileName,
      status,
      flags: flags.length,
      mode: aiEnabled ? "openai" : "demo",
    });
    if (status === "flagged") {
      await openTaskIfFlagged(supabase, profile.id, invoice.id, ex.invoice_number ?? fileName, ex.supplier_name, flags);
    }

    revalidatePath("/invoices");
    revalidatePath("/");
    return { id: invoice.id as string };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Processing failed" };
  }
}

/** Creates an empty invoice for manual keying (no document). */
export async function createManualInvoice() {
  const { supabase, profile } = await requireUser();
  const { data, error } = await supabase
    .from("invoices")
    .insert({ status: "flagged", currency: "SGD", confidence: 1, file_name: "Manual entry", uploaded_by: profile.id })
    .select("id")
    .single();
  if (error || !data) throw new Error(error?.message ?? "Could not create invoice");
  await audit(supabase, profile.id, "invoice", data.id, "created manually");
  redirect(`/invoices/${data.id}?edit=1`);
}

// ---------------------------------------------------------------------------
// Update
// ---------------------------------------------------------------------------
/** Saves human corrections, then re-runs every check against the PO. */
export async function saveInvoice(id: string, header: InvoiceHeaderInput, lines: InvoiceLineInput[]) {
  const { supabase, profile } = await requireUser();
  const { data: existing } = await supabase.from("invoices").select("status, confidence").eq("id", id).single();
  if (!existing) return { error: "Invoice not found." };
  if (existing.status === "approved" || existing.status === "rejected") {
    return { error: "Decided invoices can no longer be edited." };
  }

  const clean = lines
    .filter((l) => l.description.trim())
    .map((l) => ({
      sku: l.sku?.trim() || null,
      description: l.description.trim(),
      quantity: l.quantity,
      unit_price: l.unit_price,
      amount: Math.round(l.quantity * l.unit_price * 100) / 100,
    }));
  // A human has checked the values, so confidence is no longer a concern.
  const { po, flags, status } = await runChecks(supabase, { ...header, confidence: 1, lines: clean }, id);

  const { error } = await supabase
    .from("invoices")
    .update({
      ...header,
      currency: header.currency || "SGD",
      supplier_id: po?.supplier_id ?? null,
      po_id: po?.id ?? null,
      confidence: 1,
      status,
    })
    .eq("id", id);
  if (error) return { error: error.message };

  await supabase.from("invoice_lines").delete().eq("invoice_id", id);
  if (clean.length) await supabase.from("invoice_lines").insert(clean.map((l) => ({ ...l, invoice_id: id })));
  await supabase.from("invoice_flags").delete().eq("invoice_id", id);
  if (flags.length) await supabase.from("invoice_flags").insert(flags.map((f) => ({ ...f, invoice_id: id })));

  await syncExceptionTask(
    supabase,
    profile.id,
    "invoice",
    id,
    status === "flagged",
    `Review invoice ${header.invoice_number ?? "invoice"} (${header.supplier_name ?? "unknown supplier"})`,
    flags.filter((f) => f.severity !== "low").map((f) => `• ${f.message}`).join("\n"),
    flags.some((f) => f.severity === "high") ? "high" : "medium",
  );
  await audit(supabase, profile.id, "invoice", id, "edited", { status, flags: flags.length });

  revalidatePath(`/invoices/${id}`);
  revalidatePath("/invoices");
  revalidatePath("/");
  return { status };
}

export async function reviewInvoice(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can approve or reject invoices.");

  const id = String(formData.get("id"));
  const decision = String(formData.get("decision")) as "approved" | "rejected";
  const note = String(formData.get("note") ?? "").trim() || null;
  if (decision !== "approved" && decision !== "rejected") throw new Error("Invalid decision");

  await supabase
    .from("invoices")
    .update({ status: decision, review_note: note, reviewed_by: profile.id, reviewed_at: new Date().toISOString() })
    .eq("id", id);
  await closeExceptionTasks(supabase, "invoice", id);
  await audit(supabase, profile.id, "invoice", id, decision, note ? { note } : undefined);

  revalidatePath(`/invoices/${id}`);
  revalidatePath("/invoices");
  revalidatePath("/");
}

/** Re-opens a decided invoice so it can be corrected and re-checked. */
export async function reopenInvoice(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can reopen invoices.");
  const id = String(formData.get("id"));
  await supabase
    .from("invoices")
    .update({ status: "flagged", reviewed_by: null, reviewed_at: null, review_note: null })
    .eq("id", id);
  await audit(supabase, profile.id, "invoice", id, "reopened");
  revalidatePath(`/invoices/${id}`);
  revalidatePath("/invoices");
}

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------
export async function deleteInvoice(formData: FormData) {
  const { supabase, profile } = await requireUser();
  if (!canReview(profile)) throw new Error("Only reviewers and admins can delete invoices.");
  const id = String(formData.get("id"));

  const { data: inv } = await supabase.from("invoices").select("invoice_number, file_path").eq("id", id).single();
  await deleteExceptionTasks(supabase, "invoice", id);
  const { error } = await supabase.from("invoices").delete().eq("id", id);
  if (error) throw new Error(error.message);
  await removeDocument(supabase, inv?.file_path ?? null);
  await audit(supabase, profile.id, "invoice", id, "deleted", { invoice_number: inv?.invoice_number ?? null });

  revalidatePath("/invoices");
  revalidatePath("/");
  redirect("/invoices");
}
