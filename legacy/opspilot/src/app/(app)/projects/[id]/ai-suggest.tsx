"use client";

import { useState, useTransition } from "react";
import { Sparkles, Loader2, Check } from "lucide-react";
import type { TaskSuggestion } from "@/lib/ai";
import { StatusBadge } from "@/components/ui";
import { addSuggestedTasks, generateTaskSuggestions } from "../actions";

export function AiSuggest({ projectId, defaultBrief }: { projectId: string; defaultBrief: string }) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState(defaultBrief);
  const [suggestions, setSuggestions] = useState<TaskSuggestion[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function generate() {
    setError(null);
    startTransition(async () => {
      const res = await generateTaskSuggestions(projectId, brief);
      if (res.error) setError(res.error);
      setSuggestions(res.tasks);
      setSelected(new Set(res.tasks.map((_, i) => i)));
    });
  }

  function add() {
    const picked = suggestions.filter((_, i) => selected.has(i));
    startTransition(async () => {
      await addSuggestedTasks(projectId, picked);
      setSuggestions([]);
      setOpen(false);
    });
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn-secondary mb-4">
        <Sparkles className="size-4 text-brand-600" /> Suggest tasks with AI
      </button>
    );
  }

  return (
    <section className="card mb-6 border-brand-100 p-5">
      <h2 className="mb-1 flex items-center gap-2 font-medium">
        <Sparkles className="size-4 text-brand-600" /> AI task planner
      </h2>
      <p className="mb-3 text-sm text-muted">Describe the project and get a starter task list you can edit before adding.</p>
      <textarea className="input" rows={3} value={brief} onChange={(e) => setBrief(e.target.value)} placeholder="Project brief…" />
      <div className="mt-3 flex gap-2">
        <button className="btn-primary" onClick={generate} disabled={pending || !brief.trim()}>
          {pending && !suggestions.length ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {suggestions.length ? "Regenerate" : "Generate tasks"}
        </button>
        <button className="btn-secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

      {suggestions.length > 0 && (
        <>
          <ul className="mt-4 divide-y divide-line rounded-lg border border-line">
            {suggestions.map((s, i) => (
              <li key={i}>
                <label className="flex cursor-pointer gap-3 px-4 py-3 hover:bg-canvas/60">
                  <input
                    type="checkbox"
                    className="mt-1 accent-brand-600"
                    checked={selected.has(i)}
                    onChange={() =>
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (next.has(i)) next.delete(i);
                        else next.add(i);
                        return next;
                      })
                    }
                  />
                  <div className="flex-1 text-sm">
                    <div className="font-medium">{s.title}</div>
                    <div className="text-muted">{s.description}</div>
                  </div>
                  <div className="flex flex-col items-end gap-1 text-xs text-muted">
                    <StatusBadge status={s.priority} />
                    in {s.due_in_days} days
                  </div>
                </label>
              </li>
            ))}
          </ul>
          <button className="btn-primary mt-3" onClick={add} disabled={pending || selected.size === 0}>
            <Check className="size-4" /> Add {selected.size} task(s) to board
          </button>
        </>
      )}
    </section>
  );
}
