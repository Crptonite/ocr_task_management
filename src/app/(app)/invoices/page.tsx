import Link from "next/link";
import { AlertTriangle, PenLine } from "lucide-react";
import { requireUser } from "@/lib/supabase/server";
import { Uploader } from "@/components/uploader";
import { EmptyState, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import { date, money } from "@/lib/format";
import { createManualInvoice, processInvoice } from "./actions";

const TABS = [
  { key: "queue", label: "Review queue", statuses: ["flagged"] },
  { key: "matched", label: "Auto-matched", statuses: ["matched"] },
  { key: "done", label: "Approved / rejected", statuses: ["approved", "rejected"] },
  { key: "all", label: "All", statuses: [] as string[] },
];

export default async function InvoicesPage({ searchParams }: PageProps<"/invoices">) {
  const { supabase } = await requireUser();
  const { tab: tabParam } = await searchParams;
  const tab = TABS.find((t) => t.key === tabParam) ?? TABS[0];

  const { data: all } = await supabase
    .from("invoices")
    .select("id, invoice_number, supplier_name, po_number, invoice_date, total, currency, status, created_at, invoice_flags(severity)")
    .order("created_at", { ascending: false });

  const invoices = (all ?? []).filter((i) => tab.statuses.length === 0 || tab.statuses.includes(i.status));
  const countFor = (statuses: string[]) =>
    (all ?? []).filter((i) => statuses.length === 0 || statuses.includes(i.status)).length;

  return (
    <>
      <PageHeader
        title="Invoice checking"
        description="Upload supplier invoices. AI extracts the details, compares them with the purchase order, and sends mismatches here for review."
        actions={
          <form action={createManualInvoice}>
            <button className="btn-secondary">
              <PenLine className="size-4" /> Enter manually
            </button>
          </form>
        }
      />

      <div className="mb-6">
        <Uploader
          folder="invoices"
          title="Upload a supplier invoice"
          hint="PDF or photo, up to 10 MB. Drag and drop works too."
          process={processInvoice}
          detailBase="/invoices"
        />
      </div>

      <div className="card overflow-hidden">
        <Tabs
          active={tab.key}
          items={TABS.map((t) => ({ key: t.key, label: t.label, href: `/invoices?tab=${t.key}`, count: countFor(t.statuses) }))}
        />
        {invoices.length === 0 ? (
          <EmptyState title={tab.key === "queue" ? "Nothing waiting for review" : "No invoices here yet"}>
            {tab.key === "queue" ? "Flagged invoices will appear here." : "Upload an invoice to get started."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-line bg-canvas/50">
                <tr>
                  <th className="th">Invoice</th>
                  <th className="th">Supplier</th>
                  <th className="th">PO</th>
                  <th className="th">Date</th>
                  <th className="th text-right">Total</th>
                  <th className="th">Issues</th>
                  <th className="th">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {invoices.map((inv) => {
                  const flags = (inv.invoice_flags ?? []) as { severity: string }[];
                  const serious = flags.filter((f) => f.severity !== "low").length;
                  return (
                    <tr key={inv.id} className="hover:bg-canvas/60">
                      <td className="td font-medium">
                        <Link href={`/invoices/${inv.id}`} className="hover:text-brand-600 hover:underline">
                          {inv.invoice_number ?? "Unnumbered"}
                        </Link>
                      </td>
                      <td className="td">{inv.supplier_name ?? "—"}</td>
                      <td className="td font-mono text-xs">{inv.po_number ?? "—"}</td>
                      <td className="td text-muted">{date(inv.invoice_date)}</td>
                      <td className="td text-right tabular-nums">{money(inv.total, inv.currency ?? "SGD")}</td>
                      <td className="td">
                        {serious > 0 ? (
                          <span className="inline-flex items-center gap-1 text-amber-700">
                            <AlertTriangle className="size-3.5" /> {serious}
                          </span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="td">
                        <StatusBadge status={inv.status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
