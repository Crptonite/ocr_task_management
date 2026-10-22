import type { ReactNode } from "react";

const tones = {
  green: "bg-brand-50 text-brand-700 ring-brand-100",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  gray: "bg-stone-100 text-stone-600 ring-stone-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
} as const;
export type Tone = keyof typeof tones;

export function Badge({ tone = "gray", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>
      {children}
    </span>
  );
}

const statusMap: Record<string, { label: string; tone: Tone }> = {
  // invoices
  matched: { label: "Matched", tone: "green" },
  flagged: { label: "Flagged", tone: "amber" },
  approved: { label: "Approved", tone: "blue" },
  rejected: { label: "Rejected", tone: "red" },
  // orders
  needs_attention: { label: "Needs attention", tone: "amber" },
  ready: { label: "Ready", tone: "green" },
  exported: { label: "Exported", tone: "violet" },
  // projects / tasks
  planning: { label: "Planning", tone: "gray" },
  active: { label: "Active", tone: "green" },
  on_hold: { label: "On hold", tone: "amber" },
  done: { label: "Done", tone: "blue" },
  todo: { label: "To do", tone: "gray" },
  in_progress: { label: "In progress", tone: "blue" },
  review: { label: "In review", tone: "violet" },
  // severity / priority
  high: { label: "High", tone: "red" },
  medium: { label: "Medium", tone: "amber" },
  low: { label: "Low", tone: "gray" },
};

export function StatusBadge({ status }: { status: string }) {
  const s = statusMap[status] ?? { label: status, tone: "gray" as Tone };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between text-sm text-muted">
        <span>{label}</span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="px-6 py-14 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Tabs({ items, active }: { items: { href: string; label: string; count?: number; key: string }[]; active: string }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-line px-2">
      {items.map((t) => (
        <a
          key={t.key}
          href={t.href}
          className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm whitespace-nowrap ${
            t.key === active ? "border-brand-600 font-medium text-ink" : "border-transparent text-muted hover:text-ink"
          }`}
        >
          {t.label}
          {t.count != null && <span className="rounded-full bg-canvas px-1.5 text-xs text-muted">{t.count}</span>}
        </a>
      ))}
    </div>
  );
}
