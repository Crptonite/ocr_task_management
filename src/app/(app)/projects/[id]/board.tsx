"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CalendarDays, FileCheck2, PackageSearch, Search, Trash2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import type { Profile } from "@/lib/supabase/server";
import { StatusBadge } from "@/components/ui";
import { date, initials, isOverdue } from "@/lib/format";
import { deleteTask, updateTask } from "../actions";

export type Task = {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: "todo" | "in_progress" | "review" | "done";
  priority: "low" | "medium" | "high";
  assignee_id: string | null;
  due_date: string | null;
  source_type: "invoice" | "order" | null;
  source_id: string | null;
};

const COLUMNS: { key: Task["status"]; label: string; accent: string }[] = [
  { key: "todo", label: "To do", accent: "bg-stone-400" },
  { key: "in_progress", label: "In progress", accent: "bg-sky-500" },
  { key: "review", label: "In review", accent: "bg-violet-500" },
  { key: "done", label: "Done", accent: "bg-brand-500" },
];

export function Board({ projectId, tasks, members }: { projectId: string; tasks: Task[]; members: Profile[] }) {
  const router = useRouter();
  const [items, setItems] = useState(tasks);
  const [query, setQuery] = useState("");
  const [assignee, setAssignee] = useState("all");
  const [priority, setPriority] = useState("all");
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  // Reset local (optimistic) state whenever the server sends a fresh task list.
  const [prevTasks, setPrevTasks] = useState(tasks);
  if (tasks !== prevTasks) {
    setPrevTasks(tasks);
    setItems(tasks);
  }

  // Realtime: refresh when anyone changes a task in this project.
  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel(`tasks-${projectId}`)
      .on("postgres_changes", { event: "*", schema: "public", table: "tasks", filter: `project_id=eq.${projectId}` }, () =>
        router.refresh(),
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [projectId, router]);

  const memberById = useMemo(() => new Map(members.map((m) => [m.id, m])), [members]);

  const visible = items.filter(
    (t) =>
      (assignee === "all" || (assignee === "none" ? !t.assignee_id : t.assignee_id === assignee)) &&
      (priority === "all" || t.priority === priority) &&
      (!query || t.title.toLowerCase().includes(query.toLowerCase())),
  );

  function patch(id: string, change: Partial<Task>) {
    setItems((prev) => prev.map((t) => (t.id === id ? { ...t, ...change } : t)));
    startTransition(() => updateTask(id, change));
  }

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <input className="input pl-9" placeholder="Search tasks" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <select className="input w-44" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <option value="all">All assignees</option>
          <option value="none">Unassigned</option>
          {members.map((m) => (
            <option key={m.id} value={m.id}>
              {m.full_name ?? m.email}
            </option>
          ))}
        </select>
        <select className="input w-40" value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="all">All priorities</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {COLUMNS.map((col) => {
          const colTasks = visible.filter((t) => t.status === col.key);
          return (
            <div
              key={col.key}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(col.key);
              }}
              onDragLeave={() => setDragOver(null)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(null);
                const id = e.dataTransfer.getData("text/plain");
                const task = items.find((t) => t.id === id);
                if (task && task.status !== col.key) patch(id, { status: col.key });
              }}
              className={`flex min-h-48 flex-col rounded-xl border p-2.5 transition-colors ${
                dragOver === col.key ? "border-brand-500 bg-brand-50/70" : "border-line bg-stone-100/60"
              }`}
            >
              <div className="mb-2 flex items-center gap-2 px-1.5 py-1 text-sm font-medium">
                <span className={`size-2 rounded-full ${col.accent}`} />
                {col.label}
                <span className="text-xs font-normal text-muted">{colTasks.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {colTasks.map((t) => {
                  const member = t.assignee_id ? memberById.get(t.assignee_id) : null;
                  const overdue = isOverdue(t.due_date, t.status);
                  const open = openId === t.id;
                  return (
                    <article
                      key={t.id}
                      draggable
                      onDragStart={(e) => e.dataTransfer.setData("text/plain", t.id)}
                      className="cursor-grab rounded-lg border border-line bg-surface p-3 shadow-xs active:cursor-grabbing"
                    >
                      <button className="block w-full text-left" onClick={() => setOpenId(open ? null : t.id)}>
                        <p className={`text-sm font-medium ${t.status === "done" ? "text-muted line-through" : ""}`}>{t.title}</p>
                        <div className="mt-2 flex items-center gap-2">
                          <StatusBadge status={t.priority} />
                          {t.due_date && (
                            <span className={`flex items-center gap-1 text-xs ${overdue ? "font-medium text-red-600" : "text-muted"}`}>
                              <CalendarDays className="size-3" /> {date(t.due_date)}
                            </span>
                          )}
                          <span className="ml-auto">
                            {member ? (
                              <span
                                title={member.full_name ?? member.email ?? ""}
                                className="grid size-6 place-items-center rounded-full bg-stone-200 text-[10px] font-semibold"
                              >
                                {initials(member.full_name ?? member.email)}
                              </span>
                            ) : null}
                          </span>
                        </div>
                      </button>

                      {t.source_type && t.source_id && (
                        <Link
                          href={`/${t.source_type === "invoice" ? "invoices" : "orders"}/${t.source_id}`}
                          className="mt-2 flex items-center gap-1.5 text-xs text-brand-600 hover:underline"
                        >
                          {t.source_type === "invoice" ? <FileCheck2 className="size-3.5" /> : <PackageSearch className="size-3.5" />}
                          Open linked {t.source_type}
                        </Link>
                      )}

                      {open && (
                        <div className="mt-3 space-y-2 border-t border-line pt-3">
                          <input
                            className="input py-1.5 text-xs font-medium"
                            defaultValue={t.title}
                            aria-label="Title"
                            onBlur={(e) => {
                              const title = e.target.value.trim();
                              if (title && title !== t.title) patch(t.id, { title });
                            }}
                          />
                          <textarea
                            className="input py-1.5 text-xs"
                            rows={3}
                            defaultValue={t.description ?? ""}
                            placeholder="Add details…"
                            aria-label="Description"
                            onBlur={(e) => {
                              const description = e.target.value.trim() || null;
                              if (description !== t.description) patch(t.id, { description });
                            }}
                          />
                          <select
                            className="input py-1.5 text-xs"
                            value={t.status}
                            onChange={(e) => patch(t.id, { status: e.target.value as Task["status"] })}
                            aria-label="Status"
                          >
                            {COLUMNS.map((c) => (
                              <option key={c.key} value={c.key}>
                                {c.label}
                              </option>
                            ))}
                          </select>
                          <select
                            className="input py-1.5 text-xs"
                            value={t.assignee_id ?? ""}
                            onChange={(e) => patch(t.id, { assignee_id: e.target.value || null })}
                            aria-label="Assignee"
                          >
                            <option value="">Unassigned</option>
                            {members.map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.full_name ?? m.email}
                              </option>
                            ))}
                          </select>
                          <div className="flex gap-2">
                            <select
                              className="input py-1.5 text-xs"
                              value={t.priority}
                              onChange={(e) => patch(t.id, { priority: e.target.value as Task["priority"] })}
                              aria-label="Priority"
                            >
                              <option value="low">Low</option>
                              <option value="medium">Medium</option>
                              <option value="high">High</option>
                            </select>
                            <input
                              type="date"
                              className="input py-1.5 text-xs"
                              value={t.due_date ?? ""}
                              onChange={(e) => patch(t.id, { due_date: e.target.value || null })}
                              aria-label="Due date"
                            />
                          </div>
                          <button
                            className="flex items-center gap-1 text-xs text-red-600 hover:underline"
                            onClick={() => {
                              if (!confirm(`Delete "${t.title}"?`)) return;
                              setItems((prev) => prev.filter((x) => x.id !== t.id));
                              startTransition(() => deleteTask(t.id));
                            }}
                          >
                            <Trash2 className="size-3.5" /> Delete task
                          </button>
                        </div>
                      )}
                    </article>
                  );
                })}
                {colTasks.length === 0 && <p className="px-2 py-6 text-center text-xs text-muted">Drop tasks here</p>}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
