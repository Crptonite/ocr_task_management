import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CalendarDays, Pencil, Trash2 } from "lucide-react";
import { ConfirmButton } from "@/components/confirm-button";
import { requireUser, type Profile } from "@/lib/supabase/server";
import { StatusBadge } from "@/components/ui";
import { date, isOverdue } from "@/lib/format";
import { Board, type Task } from "./board";
import { AiSuggest } from "./ai-suggest";
import { ProjectStatusSelect } from "./status-select";
import { createTask, deleteProject, updateProject } from "../actions";

export default async function ProjectDetail({ params }: PageProps<"/projects/[id]">) {
  const { id } = await params;
  const { supabase } = await requireUser();

  const [{ data: project }, { data: tasks }, { data: members }] = await Promise.all([
    supabase.from("projects").select("*").eq("id", id).maybeSingle(),
    supabase.from("tasks").select("*").eq("project_id", id).order("created_at"),
    supabase.from("profiles").select("id, full_name, email, role").order("full_name"),
  ]);
  if (!project) notFound();

  const all = (tasks ?? []) as Task[];
  const done = all.filter((t) => t.status === "done").length;
  const overdue = all.filter((t) => isOverdue(t.due_date, t.status)).length;
  const isException = project.name === "Invoice Exceptions" || project.name === "Order Exceptions";

  return (
    <>
      <Link href="/projects" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Projects
      </Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{project.name}</h1>
            <StatusBadge status={project.status} />
          </div>
          {project.description && <p className="mt-1 text-sm text-muted">{project.description}</p>}
          <p className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted">
            <span className="flex items-center gap-1">
              <CalendarDays className="size-3.5" /> Due {date(project.due_date)}
            </span>
            <span>
              {done}/{all.length} done
            </span>
            {overdue > 0 && <span className="text-red-600">{overdue} overdue</span>}
          </p>
        </div>
        <ProjectStatusSelect id={project.id} status={project.status} />
      </div>

      <details className="card group mb-6">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-3 text-sm font-medium">
          <Pencil className="size-4 text-muted" /> Edit or delete project
        </summary>
        <div className="border-t border-line p-5">
          <form action={updateProject} className="grid gap-4 sm:grid-cols-3">
            <input type="hidden" name="id" value={project.id} />
            <label className="sm:col-span-2">
              <span className="label">Project name</span>
              <input name="name" className="input" defaultValue={project.name} required />
            </label>
            <label>
              <span className="label">Due date</span>
              <input name="due_date" type="date" className="input" defaultValue={project.due_date ?? ""} />
            </label>
            <label className="sm:col-span-3">
              <span className="label">Brief</span>
              <textarea name="description" rows={3} className="input" defaultValue={project.description ?? ""} />
            </label>
            <div className="sm:col-span-3">
              <button className="btn-primary">Save changes</button>
            </div>
          </form>
          <form action={deleteProject} className="mt-4 flex items-center justify-between gap-4 rounded-lg bg-red-50/60 px-4 py-3">
            <input type="hidden" name="id" value={project.id} />
            <p className="text-sm text-red-800">Deleting a project also deletes its {all.length} task(s).</p>
            <ConfirmButton message={`Delete "${project.name}" and all of its tasks? This cannot be undone.`}>
              <Trash2 className="size-4" /> Delete project
            </ConfirmButton>
          </form>
        </div>
      </details>

      {!isException && <AiSuggest projectId={project.id} defaultBrief={project.description ?? ""} />}

      <form action={createTask} className="card mb-6 grid gap-3 p-4 sm:grid-cols-[1fr_160px_150px_150px_auto]">
        <input type="hidden" name="project_id" value={project.id} />
        <input name="title" className="input" placeholder="Add a task…" required />
        <select name="assignee_id" className="input" defaultValue="">
          <option value="">Unassigned</option>
          {(members as Profile[] | null)?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.full_name ?? m.email}
            </option>
          ))}
        </select>
        <select name="priority" className="input" defaultValue="medium">
          <option value="low">Low priority</option>
          <option value="medium">Medium priority</option>
          <option value="high">High priority</option>
        </select>
        <input name="due_date" type="date" className="input" />
        <button className="btn-primary">Add</button>
      </form>

      <Board projectId={project.id} tasks={all} members={(members ?? []) as Profile[]} />
    </>
  );
}
