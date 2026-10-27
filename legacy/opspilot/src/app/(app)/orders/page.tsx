import Link from "next/link";
import { Download, PenLine } from "lucide-react";
import { requireUser } from "@/lib/supabase/server";
import { Uploader } from "@/components/uploader";
import { Badge, EmptyState, PageHeader, StatusBadge, Tabs } from "@/components/ui";
import { date, money } from "@/lib/format";
import { createManualOrder, processOrder } from "./actions";

const TABS = [
  { key: "attention", label: "Needs attention", statuses: ["needs_attention"] },
  { key: "ready", label: "Ready to approve", statuses: ["ready"] },
  { key: "approved", label: "Approved", statuses: ["approved"] },
  { key: "exported", label: "Exported", statuses: ["exported"] },
  { key: "all", label: "All", statuses: [] as string[] },
];

export default async function OrdersPage({ searchParams }: PageProps<"/orders">) {
  const { supabase } = await requireUser();
  const { tab: tabParam } = await searchParams;
  const tab = TABS.find((t) => t.key === tabParam) ?? TABS[0];

  const { data: all } = await supabase
    .from("orders")
    .select("id, order_type, order_number, counterparty, order_date, total, currency, status, issues, created_at")
    .order("created_at", { ascending: false });

  const orders = (all ?? []).filter((o) => tab.statuses.length === 0 || tab.statuses.includes(o.status));
  const countFor = (statuses: string[]) =>
    (all ?? []).filter((o) => statuses.length === 0 || statuses.includes(o.status)).length;
  const approvedCount = countFor(["approved"]);

  return (
    <>
      <PageHeader
        title="Order automation"
        description="Turn purchase and sales order documents into validated, ERP-ready records."
        actions={
          <>
            <form action={createManualOrder}>
              <button className="btn-secondary">
                <PenLine className="size-4" /> Enter manually
              </button>
            </form>
            {approvedCount > 0 ? (
              <a href="/api/orders/export" className="btn-primary">
                <Download className="size-4" /> Export {approvedCount} to ERP (CSV)
              </a>
            ) : (
              <span className="btn-secondary pointer-events-none opacity-60">
                <Download className="size-4" /> Nothing to export
              </span>
            )}
          </>
        }
      />

      <div className="mb-6">
        <Uploader
          folder="orders"
          title="Upload an order document"
          hint="Customer PO, sales order or supplier confirmation: PDF or photo, up to 10 MB."
          process={processOrder}
          detailBase="/orders"
        />
      </div>

      <div className="card overflow-hidden">
        <Tabs
          active={tab.key}
          items={TABS.map((t) => ({
            key: t.key,
            label: t.label,
            href: `/orders?tab=${t.key}`,
            count: countFor(t.statuses),
          }))}
        />
        {orders.length === 0 ? (
          <EmptyState title="No orders here">Upload an order document to extract it.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-line bg-canvas/50">
                <tr>
                  <th className="th">Order</th>
                  <th className="th">Type</th>
                  <th className="th">Customer / supplier</th>
                  <th className="th">Date</th>
                  <th className="th text-right">Total</th>
                  <th className="th">Validation</th>
                  <th className="th">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {orders.map((o) => (
                  <tr key={o.id} className="hover:bg-canvas/60">
                    <td className="td font-medium">
                      <Link href={`/orders/${o.id}`} className="hover:text-brand-600 hover:underline">
                        {o.order_number ?? "Unnumbered"}
                      </Link>
                    </td>
                    <td className="td">
                      <Badge tone={o.order_type === "sales" ? "blue" : "violet"}>
                        {o.order_type === "sales" ? "Sales" : "Purchase"}
                      </Badge>
                    </td>
                    <td className="td">{o.counterparty ?? "—"}</td>
                    <td className="td text-muted">{date(o.order_date)}</td>
                    <td className="td text-right tabular-nums">{money(o.total, o.currency ?? "SGD")}</td>
                    <td className="td text-sm">
                      {o.issues?.length ? (
                        <span className="text-amber-700">{o.issues.length} issue(s)</span>
                      ) : (
                        <span className="text-brand-700">Passed</span>
                      )}
                    </td>
                    <td className="td">
                      <StatusBadge status={o.status} />
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
