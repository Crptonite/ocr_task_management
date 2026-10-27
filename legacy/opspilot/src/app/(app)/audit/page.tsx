import Link from "next/link";
import { requireUser } from "@/lib/supabase/server";
import { Badge, EmptyState, PageHeader, type Tone } from "@/components/ui";
import { dateTime } from "@/lib/format";

const entityTone: Record<string, Tone> = { invoice: "amber", order: "violet", project: "green", task: "blue", profile: "gray" };
const entityHref: Record<string, string> = { invoice: "/invoices", order: "/orders", project: "/projects" };

export default async function AuditPage({ searchParams }: PageProps<"/audit">) {
  const { supabase } = await requireUser();
  const { type } = await searchParams;

  let query = supabase
    .from("audit_logs")
    .select("id, entity_type, entity_id, action, details, created_at, profiles(full_name)")
    .order("created_at", { ascending: false })
    .limit(200);
  if (typeof type === "string" && type) query = query.eq("entity_type", type);
  const { data: logs } = await query;

  return (
    <>
      <PageHeader title="Audit log" description="Every upload, AI result, edit and decision, with who did it and when." />
      <div className="mb-4 flex flex-wrap gap-2 text-sm">
        {["", "invoice", "order", "project", "task", "profile"].map((t) => (
          <Link
            key={t}
            href={t ? `/audit?type=${t}` : "/audit"}
            className={`rounded-full border px-3 py-1 capitalize ${
              (type ?? "") === t ? "border-brand-600 bg-brand-50 text-brand-700" : "border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {t || "All"}
          </Link>
        ))}
      </div>
      <div className="card overflow-hidden">
        {!logs?.length ? (
          <EmptyState title="No activity yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-line bg-canvas/50">
                <tr>
                  <th className="th">When</th>
                  <th className="th">Who</th>
                  <th className="th">Record</th>
                  <th className="th">Action</th>
                  <th className="th">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td className="td whitespace-nowrap text-muted">{dateTime(l.created_at)}</td>
                    <td className="td">{(l.profiles as unknown as { full_name: string } | null)?.full_name ?? "System"}</td>
                    <td className="td">
                      {entityHref[l.entity_type] && l.entity_id ? (
                        <Link href={`${entityHref[l.entity_type]}/${l.entity_id}`}>
                          <Badge tone={entityTone[l.entity_type]}>{l.entity_type}</Badge>
                        </Link>
                      ) : (
                        <Badge tone={entityTone[l.entity_type] ?? "gray"}>{l.entity_type}</Badge>
                      )}
                    </td>
                    <td className="td">{l.action}</td>
                    <td className="td max-w-xs truncate font-mono text-xs text-muted">
                      {l.details ? Object.entries(l.details).map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ") : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
