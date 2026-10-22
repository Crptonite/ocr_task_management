import Link from "next/link";
import { CalendarDays, Plus, AlertCircle } from "lucide-react";
import { requireUser } from "@/lib/supabase/server";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { date, isOverdue } from "@/lib/format";
import { createProject } from "./actions";

export default async function ProjectsPage() {
  const { supabase } = await requireUser();
  const { data: projects } = await supabase
    .from("projects")
    .select("id, name, description, status, due_date, tasks(status, due_date)")
    .order("created_at", { ascending: true });

  return (
    <>
      <PageHeader title="Projects & tasks" description="Plan work, assign owners and deadlines, and track progress in one shared place." />

      <details className="card group mb-6">
        <summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-4 font-medium">
          <Plus className="size-4 text-brand-600 transition-transform group-open:rotate-45" /> New project
        </summary>
        <form action={createProject} className="grid gap-4 border-t border-line p-5 sm:grid-cols-3">
          <label className="sm:col-span-2">
            <span className="label">Project name</span>
            <input name="name" className="input" required placeholder="e.g. Hotel lobby fit-out – The Loft" />
          </label>
          <label>
            <span className="label">Due date</span>
            <input name="due_date" type="date" className="input" />
          </label>
          <label className="sm:col-span-3">
            <span className="label">Brief (AI uses this to suggest tasks)</span>
            <textarea
              name="description"
              rows={3}
              className="input"
              placeholder="What needs to happen, for whom, and by when?"
            />
          </label>
          <div className="sm:col-span-3">
            <button className="btn-primary">Create project</button>
          </div>
        </form>
      </details>

      {!projects?.length ? (
        <div className="card">
          <EmptyState title="No projects yet">Create your first project above.</EmptyState>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => {
            const tasks = (p.tasks ?? []) as { status: string; due_date: string | null }[];
            const done = tasks.filter((t) => t.status === "done").length;
            const overdue = tasks.filter((t) => isOverdue(t.due_date, t.status)).length;
            const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
            return (
              <Link key={p.id} href={`/projects/${p.id}`} className="card flex flex-col p-5 transition-shadow hover:shadow-md">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-medium">{p.name}</h3>
                  <StatusBadge status={p.status} />
                </div>
                <p className="mt-1 line-clamp-2 flex-1 text-sm text-muted">{p.description ?? "No description"}</p>
                <div className="mt-4">
                  <div className="mb-1.5 flex justify-between text-xs text-muted">
                    <span>
                      {done}/{tasks.length} tasks done
                    </span>
                    <span>{pct}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-canvas">
                    <div className="h-full rounded-full bg-brand-500" style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <div className="mt-4 flex items-center gap-4 text-xs text-muted">
                  <span className="flex items-center gap-1">
                    <CalendarDays className="size-3.5" /> {date(p.due_date)}
                  </span>
                  {overdue > 0 && (
                    <span className="flex items-center gap-1 text-red-600">
                      <AlertCircle className="size-3.5" /> {overdue} overdue
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </>
  );
}
