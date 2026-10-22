"use client";

import { useTransition } from "react";
import { updateProjectStatus } from "../actions";

export function ProjectStatusSelect({ id, status }: { id: string; status: string }) {
  const [pending, startTransition] = useTransition();
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted">Status</span>
      <select
        className="input w-36"
        defaultValue={status}
        disabled={pending}
        onChange={(e) => startTransition(() => updateProjectStatus(id, e.target.value))}
      >
        <option value="planning">Planning</option>
        <option value="active">Active</option>
        <option value="on_hold">On hold</option>
        <option value="done">Done</option>
      </select>
    </label>
  );
}
