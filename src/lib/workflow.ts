import "server-only";
import type { SupabaseClient } from "@supabase/supabase-js";

export async function audit(
  supabase: SupabaseClient,
  actorId: string,
  entityType: string,
  entityId: string | null,
  action: string,
  details?: Record<string, unknown>,
) {
  await supabase.from("audit_logs").insert({
    actor_id: actorId,
    entity_type: entityType,
    entity_id: entityId,
    action,
    details: details ?? null,
  });
}

export async function downloadDocument(supabase: SupabaseClient, path: string) {
  const { data, error } = await supabase.storage.from("documents").download(path);
  if (error || !data) throw new Error(`Could not read uploaded file: ${error?.message ?? "not found"}`);
  return Buffer.from(await data.arrayBuffer());
}

export async function signedUrl(supabase: SupabaseClient, path: string | null) {
  if (!path) return null;
  const { data } = await supabase.storage.from("documents").createSignedUrl(path, 60 * 30);
  return data?.signedUrl ?? null;
}

/**
 * Links the three modules: an invoice or order that needs a human becomes a
 * task on the matching exceptions board in the project tracker.
 */
export async function openExceptionTask(
  supabase: SupabaseClient,
  actorId: string,
  kind: "invoice" | "order",
  sourceId: string,
  title: string,
  description: string,
  priority: "low" | "medium" | "high",
) {
  const projectName = kind === "invoice" ? "Invoice Exceptions" : "Order Exceptions";
  let { data: project } = await supabase.from("projects").select("id").eq("name", projectName).maybeSingle();
  if (!project) {
    const created = await supabase
      .from("projects")
      .insert({ name: projectName, description: `Auto-created tasks for ${kind}s that need review.`, status: "active" })
      .select("id")
      .single();
    project = created.data;
  }
  if (!project) return;

  const due = new Date(Date.now() + 2 * 86400000).toISOString().slice(0, 10);
  await supabase.from("tasks").insert({
    project_id: project.id,
    title,
    description,
    priority,
    due_date: due,
    source_type: kind,
    source_id: sourceId,
    created_by: actorId,
  });
}

/**
 * After an edit: keep one open exception task in step with the record.
 * Updates the open task if there is one (keeping its assignee), creates one
 * if needed, or closes it when the record is now clean.
 */
export async function syncExceptionTask(
  supabase: SupabaseClient,
  actorId: string,
  kind: "invoice" | "order",
  sourceId: string,
  needsAttention: boolean,
  title: string,
  description: string,
  priority: "low" | "medium" | "high",
) {
  if (!needsAttention) return closeExceptionTasks(supabase, kind, sourceId);
  const { data: open } = await supabase
    .from("tasks")
    .select("id")
    .eq("source_type", kind)
    .eq("source_id", sourceId)
    .neq("status", "done")
    .limit(1)
    .maybeSingle();
  if (open) {
    await supabase
      .from("tasks")
      .update({ title, description, priority, updated_at: new Date().toISOString() })
      .eq("id", open.id);
  } else {
    await openExceptionTask(supabase, actorId, kind, sourceId, title, description, priority);
  }
}

export async function removeDocument(supabase: SupabaseClient, path: string | null) {
  if (path) await supabase.storage.from("documents").remove([path]);
}

export async function deleteExceptionTasks(supabase: SupabaseClient, kind: "invoice" | "order", sourceId: string) {
  await supabase.from("tasks").delete().eq("source_type", kind).eq("source_id", sourceId);
}

export async function closeExceptionTasks(supabase: SupabaseClient, kind: "invoice" | "order", sourceId: string) {
  await supabase
    .from("tasks")
    .update({ status: "done", updated_at: new Date().toISOString() })
    .eq("source_type", kind)
    .eq("source_id", sourceId)
    .neq("status", "done");
}
