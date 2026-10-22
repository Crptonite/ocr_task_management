import { requireUser } from "@/lib/supabase/server";
import { EmptyState, PageHeader, StatusBadge } from "@/components/ui";
import { date, money } from "@/lib/format";

export default async function PurchaseOrdersPage() {
  const { supabase } = await requireUser();
  const { data: pos } = await supabase
    .from("purchase_orders")
    .select("id, po_number, order_date, currency, total, status, suppliers(name), po_lines(id, sku, description, quantity, unit_price), invoices(id, status)")
    .order("po_number");

  return (
    <>
      <PageHeader
        title="Purchase orders"
        description="Existing records the invoice checker compares against. In production these would sync from the ERP."
      />
      {!pos?.length ? (
        <div className="card">
          <EmptyState title="No purchase orders">Run supabase/seed.sql to load demo data.</EmptyState>
        </div>
      ) : (
        <div className="space-y-4">
          {pos.map((po) => (
            <details key={po.id} className="card group">
              <summary className="flex cursor-pointer list-none flex-wrap items-center gap-4 px-5 py-4">
                <span className="font-mono text-sm font-medium">{po.po_number}</span>
                <span className="flex-1 text-sm">{(po.suppliers as unknown as { name: string } | null)?.name}</span>
                <span className="text-xs text-muted">{date(po.order_date)}</span>
                <span className="text-xs text-muted">{po.invoices?.length ?? 0} invoice(s)</span>
                <span className="w-28 text-right text-sm font-medium tabular-nums">{money(po.total, po.currency)}</span>
                <StatusBadge status={po.status === "open" ? "active" : "done"} />
              </summary>
              <table className="w-full border-t border-line">
                <thead className="bg-canvas/50">
                  <tr>
                    <th className="th">SKU</th>
                    <th className="th">Description</th>
                    <th className="th text-right">Qty</th>
                    <th className="th text-right">Unit price</th>
                    <th className="th text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {po.po_lines.map((l) => (
                    <tr key={l.id}>
                      <td className="td font-mono text-xs">{l.sku}</td>
                      <td className="td">{l.description}</td>
                      <td className="td text-right tabular-nums">{Number(l.quantity)}</td>
                      <td className="td text-right tabular-nums">{money(l.unit_price, po.currency)}</td>
                      <td className="td text-right tabular-nums">{money(Number(l.quantity) * Number(l.unit_price), po.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ))}
        </div>
      )}
    </>
  );
}
