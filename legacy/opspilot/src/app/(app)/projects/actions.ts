"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/supabase/server";
import { suggestTasks, type TaskSuggestion } from "@/lib/ai";
import { audit } from "@/lib/workflow";

const STATUSES = ["todo", "in_progress", "review", "done"] as const;
type TaskStatus = (typeof STATUSES)[number];

export async function createProject(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const name = String(formData.get("name") ?? "").trim();
  if (!name) return;
  const { data } = await supabase
    .from("projects")
    .insert({
      name,
      description: String(formData.get("description") ?? "").trim() || null,
      due_date: String(formData.get("due_date") ?? "") || null,
      owner_id: profile.id,
      status: "active",
    })
    .select("id")
    .single();
  if (data) await audit(supabase, profile.id, "project", data.id, "created", { name });
  revalidatePath("/projects");
  if (data) redirect(`/projects/${data.id}`);
}

export async function updateProject(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const id = String(formData.get("id"));
  const name = String(formData.get("name") ?? "").trim();
  if (!name) return;
  const patch = {
    name,
    description: String(formData.get("description") ?? "").trim() || null,
    due_date: String(formData.get("due_date") ?? "") || null,
  };
  await supabase.from("projects").update(patch).eq("id", id);
  await audit(supabase, profile.id, "project", id, "edited", patch);
  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
}

export async function deleteProject(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const id = String(formData.get("id"));
  const { data } = await supabase.from("projects").delete().eq("id", id).select("name").single();
  await audit(supabase, profile.id, "project", id, "deleted", data ? { name: data.name } : undefined);
  revalidatePath("/projects");
  revalidatePath("/");
  redirect("/projects");
}

export async function updateProjectStatus(id: string, status: string) {
  const { supabase, profile } = await requireUser();
  await supabase.from("projects").update({ status }).eq("id", id);
  await audit(supabase, profile.id, "project", id, `status → ${status}`);
  revalidatePath(`/projects/${id}`);
  revalidatePath("/projects");
}

export async function createTask(formData: FormData) {
  const { supabase, profile } = await requireUser();
  const projectId = String(formData.get("project_id"));
  const title = String(formData.get("title") ?? "").trim();
  if (!title) return;
  const { data } = await supabase
    .from("tasks")
    .insert({
      project_id: projectId,
      title,
      description: String(formData.get("description") ?? "").trim() || null,
      priority: String(formData.get("priority") ?? "medium"),
      assignee_id: String(formData.get("assignee_id") ?? "") || null,
      due_date: String(formData.get("due_date") ?? "") || null,
      created_by: profile.id,
    })
    .select("id")
    .single();
  if (data) await audit(supabase, profile.id, "task", data.id, "created", { title });
  revalidatePath(`/projects/${projectId}`);
}

export async function updateTask(
  id: string,
  patch: Partial<{
    title: string;
    description: string | null;
    status: TaskStatus;
    priority: string;
    assignee_id: string | null;
    due_date: string | null;
  }>,
) {
  const { supabase, profile } = await requireUser();
  if (patch.status && !STATUSES.includes(patch.status)) throw new Error("Invalid status");
  const { data } = await supabase
    .from("tasks")
    .update({ ...patch, updated_at: new Date().toISOString() })
    .eq("id", id)
    .select("project_id")
    .single();
  await audit(supabase, profile.id, "task", id, "updated", patch);
  if (data) revalidatePath(`/projects/${data.project_id}`);
}

export async function deleteTask(id: string) {
  const { supabase, profile } = await requireUser();
  const { data } = await supabase.from("tasks").delete().eq("id", id).select("project_id, title").single();
  await audit(supabase, profile.id, "task", id, "deleted", data ? { title: data.title } : undefined);
  if (data) revalidatePath(`/projects/${data.project_id}`);
}

export async function generateTaskSuggestions(projectId: string, brief: string) {
  const { supabase } = await requireUser();
  const { data: project } = await supabase.from("projects").select("name").eq("id", projectId).single();
  try {
    return { tasks: await suggestTasks(brief, project?.name ?? "Project") };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "AI suggestion failed", tasks: [] as TaskSuggestion[] };
  }
}

export async function addSuggestedTasks(projectId: string, tasks: TaskSuggestion[]) {
  const { supabase, profile } = await requireUser();
  const today = Date.now();
  await supabase.from("tasks").insert(
    tasks.map((t) => ({
      project_id: projectId,
      title: t.title,
      description: t.description,
      priority: t.priority,
      due_date: new Date(today + t.due_in_days * 86400000).toISOString().slice(0, 10),
      created_by: profile.id,
    })),
  );
  await audit(supabase, profile.id, "project", projectId, "added AI-suggested tasks", { count: tasks.length });
  revalidatePath(`/projects/${projectId}`);
}
