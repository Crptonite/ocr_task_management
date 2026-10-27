import Link from "next/link";
import { ArrowRight, Clock, FileCheck2, KanbanSquare, PackageSearch, ShieldAlert } from "lucide-react";
import { requireUser } from "@/lib/supabase/server";
import { PageHeader, Stat, StatusBadge } from "@/components/ui";
import { date, dateTime, isOverdue, money } from "@/lib/format";

// Rough manual-handling benchmarks used for the "time saved" estimate.
const MANUAL_MIN_PER_INVOICE = 12;
const MANUAL_MIN_PER_ORDER = 15;
const REVIEW_MIN_PER_EXCEPTION = 4;

export default async function Dashboard() {
  const { supabase, profile } = await requireUser();

  const [{ data: invoices }, { data: orders }, { data: tasks }, { data: activity }] = await Promise.all([
    supabase.from("invoices").select("id, status, total, currency, invoice_number, supplier_name, created_at, invoice_flags(severity, code)"),
    supabase.from("orders").select("id, status"),
    supabase.from("tasks").select("id, title, status, due_date, priority, project_id, assignee_id, projects(name)"),
    supabase
      .from("audit_logs")
      .select("id, entity_type, entity_id, action, created_at, profiles(full_name)")
      .order("created_at", { ascending: false })
      .limit(8),
  ]);

  const inv = invoices ?? [];
  const flagged = inv.filter((i) => i.status === "flagged");
  const withIssues = inv.filter((i) => (i.invoice_flags ?? []).some((f: { severity: string }) => f.severity !== "low"));
  const mismatchRate = inv.length ? Math.round((withIssues.length / inv.length) * 100) : 0;
  const flaggedValue = flagged.reduce((s, i) => s + Number(i.total ?? 0), 0);

  const ord = orders ?? [];
  const exceptions = flagged.length + ord.filter((o) => o.status === "needs_attention").length;
  const minutesSaved = Math.max(
    0,
    inv.length * MANUAL_MIN_PER_INVOICE + ord.length * MANUAL_MIN_PER_ORDER - exceptions * REVIEW_MIN_PER_EXCEPTION,
  );

  const allTasks = tasks ?? [];
  const openTasks = allTasks.filter((t) => t.status !== "done");
  const overdue = openTasks.filter((t) => isOverdue(t.due_date, t.status));
  const mine = openTasks
    .filter((t) => t.assignee_id === profile.id || overdue.includes(t))
    .sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999"))
    .slice(0, 6);

  // Most common issue types across all invoices.
  const codeCounts = new Map<string, number>();
  for (const i of inv) for (const f of (i.invoice_flags ?? []) as { code: string; severity: string }[]) {
    if (f.severity !== "low") codeCounts.set(f.code, (codeCounts.get(f.code) ?? 0) + 1);
  }
  const topIssues = [...codeCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxIssue = topIssues[0]?.[1] ?? 1;

  const firstName = (profile.full_name ?? "").split(" ")[0];

  return (
    <>
      <PageHeader title={`Good day${firstName ? `, ${firstName}` : ""}`} description="Here's what needs your attention across invoices, orders and projects." />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat
          label="Invoices to review"
          value={flagged.length}
          hint={flagged.length ? `${money(flaggedValue)} on hold` : "Queue is clear"}
          icon={<ShieldAlert className="size-4" />}
        />
        <Stat label="Mismatch rate" value={`${mismatchRate}%`} hint={`${inv.length} invoices checked`} icon={<FileCheck2 className="size-4" />} />
        <Stat
          label="Orders awaiting action"
          value={ord.filter((o) => o.status === "needs_attention" || o.status === "ready").length}
          hint={`${ord.filter((o) => o.status === "approved").length} ready to export`}
          icon={<PackageSearch className="size-4" />}
        />
        <Stat
          label="Est. time saved"
          value={`${(minutesSaved / 60).toFixed(1)} h`}
          hint="vs. manual keying & checking"
          icon={<Clock className="size-4" />}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="font-medium">Review queue</h2>
            <Link href="/invoices" className="flex items-center gap-1 text-sm text-brand-600 hover:underline">
              All invoices <ArrowRight className="size-3.5" />
            </Link>
          </header>
          {flagged.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-muted">No invoices waiting for review.</p>
          ) : (
            <ul className="divide-y divide-line">
              {flagged.slice(0, 5).map((i) => (
                <li key={i.id}>
                  <Link href={`/invoices/${i.id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-canvas/60">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{i.invoice_number ?? "Unnumbered"}</p>
                      <p className="truncate text-xs text-muted">{i.supplier_name}</p>
                    </div>
                    <span className="text-xs text-amber-700">
                      {(i.invoice_flags ?? []).filter((f: { severity: string }) => f.severity !== "low").length} issue(s)
                    </span>
                    <span className="w-28 text-right text-sm tabular-nums">{money(i.total, i.currency ?? "SGD")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-5">
          <h2 className="mb-4 font-medium">Most common invoice issues</h2>
          {topIssues.length === 0 ? (
            <p className="text-sm text-muted">No issues found yet.</p>
          ) : (
            <ul className="space-y-3">
              {topIssues.map(([code, n]) => (
                <li key={code}>
                  <div className="mb-1 flex justify-between text-xs">
                    <span className="font-mono">{code.replaceAll("_", " ").toLowerCase()}</span>
                    <span className="text-muted">{n}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-canvas">
                    <div className="h-full rounded-full bg-amber-500" style={{ width: `${(n / maxIssue) * 100}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card lg:col-span-2">
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="font-medium">My tasks & overdue work</h2>
            <span className="text-xs text-muted">
              {openTasks.length} open · <span className={overdue.length ? "text-red-600" : ""}>{overdue.length} overdue</span>
            </span>
          </header>
          {mine.length === 0 ? (
            <p className="px-5 py-10 text-center text-sm text-muted">Nothing assigned to you or overdue.</p>
          ) : (
            <ul className="divide-y divide-line">
              {mine.map((t) => (
                <li key={t.id}>
                  <Link href={`/projects/${t.project_id}`} className="flex items-center gap-4 px-5 py-3 hover:bg-canvas/60">
                    <KanbanSquare className="size-4 shrink-0 text-muted" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm">{t.title}</p>
                      <p className="truncate text-xs text-muted">{(t.projects as unknown as { name: string } | null)?.name}</p>
                    </div>
                    <StatusBadge status={t.priority} />
                    <span className={`w-24 text-right text-xs ${isOverdue(t.due_date, t.status) ? "font-medium text-red-600" : "text-muted"}`}>
                      {date(t.due_date)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-medium">Recent activity</h2>
            <Link href="/audit" className="text-xs text-brand-600 hover:underline">
              Audit log
            </Link>
          </div>
          <ol className="space-y-3">
            {(activity ?? []).map((a) => (
              <li key={a.id} className="text-sm">
                <span className="font-medium">{(a.profiles as unknown as { full_name: string } | null)?.full_name ?? "System"}</span>{" "}
                <span className="text-muted">
                  {a.action} {a.entity_type}
                </span>
                <div className="text-xs text-muted">{dateTime(a.created_at)}</div>
              </li>
            ))}
            {!activity?.length && <p className="text-sm text-muted">No activity yet.</p>}
          </ol>
        </section>
      </div>
    </>
  );
}
