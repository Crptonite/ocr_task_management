import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, AlertOctagon, AlertTriangle, Info, CheckCircle2, Pencil, Trash2, RotateCcw } from "lucide-react";
import { canReview, requireUser } from "@/lib/supabase/server";
import { signedUrl } from "@/lib/workflow";
import { findPoLine } from "@/lib/matching";
import { StatusBadge } from "@/components/ui";
import { DocumentPreview } from "@/components/document-preview";
import { ConfirmButton } from "@/components/confirm-button";
import { date, dateTime, money } from "@/lib/format";
import { deleteInvoice, reopenInvoice, reviewInvoice } from "../actions";
import { InvoiceEditor } from "./invoice-editor";

const severityIcon = {
  high: <AlertOctagon className="size-4 text-red-600" />,
  medium: <AlertTriangle className="size-4 text-amber-600" />,
  low: <Info className="size-4 text-stone-500" />,
};

export default async function InvoiceDetail({ params, searchParams }: PageProps<"/invoices/[id]">) {
  const { id } = await params;
  const { edit } = await searchParams;
  const { supabase, profile } = await requireUser();

  const { data: inv } = await supabase
    .from("invoices")
    .select("*, invoice_lines(*), invoice_flags(*), reviewer:profiles!invoices_reviewed_by_fkey(full_name)")
    .eq("id", id)
    .maybeSingle();
  if (!inv) notFound();

  const [{ data: po }, { data: history }, url] = await Promise.all([
    inv.po_id
      ? supabase
          .from("purchase_orders")
          .select("po_number, order_date, total, suppliers(name), po_lines(*)")
          .eq("id", inv.po_id)
          .single()
      : Promise.resolve({ data: null }),
    supabase
      .from("audit_logs")
      .select("id, action, created_at, details, profiles(full_name)")
      .eq("entity_id", id)
      .order("created_at", { ascending: false }),
    signedUrl(supabase, inv.file_path),
  ]);

  const currency = inv.currency ?? "SGD";
  const lines = (inv.invoice_lines ?? []) as { id: string; sku: string | null; description: string; quantity: number; unit_price: number; amount: number }[];
  const poLines = ((po?.po_lines ?? []) as { sku: string | null; description: string; quantity: number; unit_price: number }[]).map((l) => ({
    ...l,
    quantity: Number(l.quantity),
    unit_price: Number(l.unit_price),
  }));
  const flags = ((inv.invoice_flags ?? []) as { id: string; severity: "high" | "medium" | "low"; message: string; expected: string | null; actual: string | null; code: string }[]).sort(
    (a, b) => ["high", "medium", "low"].indexOf(a.severity) - ["high", "medium", "low"].indexOf(b.severity),
  );
  const decided = inv.status === "approved" || inv.status === "rejected";
  const editing = edit === "1" && !decided;
  const reviewer = inv.reviewer as { full_name: string | null } | null;
  const { data: poList } = editing
    ? await supabase.from("purchase_orders").select("po_number").order("po_number")
    : { data: null };

  return (
    <>
      <Link href="/invoices" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Invoices
      </Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{inv.invoice_number ?? "Unnumbered invoice"}</h1>
            <StatusBadge status={inv.status} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {inv.supplier_name ?? "Unknown supplier"} · {inv.file_name} · AI confidence{" "}
            {Math.round(Number(inv.confidence ?? 0) * 100)}%
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-xs text-muted">Invoice total</div>
            <div className="text-2xl font-semibold tabular-nums">{money(inv.total, currency)}</div>
          </div>
          {!decided && !editing && (
            <Link href={`/invoices/${inv.id}?edit=1`} className="btn-secondary">
              <Pencil className="size-4" /> Edit
            </Link>
          )}
          {decided && canReview(profile) && (
            <form action={reopenInvoice}>
              <input type="hidden" name="id" value={inv.id} />
              <button className="btn-secondary">
                <RotateCcw className="size-4" /> Reopen
              </button>
            </form>
          )}
          {canReview(profile) && (
            <form action={deleteInvoice}>
              <input type="hidden" name="id" value={inv.id} />
              <ConfirmButton
                message="Delete this invoice, its file and its exception task? This cannot be undone."
                className="btn-secondary text-red-700"
              >
                <Trash2 className="size-4" /> Delete
              </ConfirmButton>
            </form>
          )}
        </div>
      </div>

      {editing ? (
        <div className="grid gap-6 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <DocumentPreview url={url} fileName={inv.file_name} />
          </div>
          <div className="lg:col-span-3">
            <InvoiceEditor
              id={inv.id}
              poNumbers={(poList ?? []).map((p) => p.po_number)}
              initialHeader={{
                invoice_number: inv.invoice_number,
                supplier_name: inv.supplier_name,
                po_number: inv.po_number,
                invoice_date: inv.invoice_date,
                due_date: inv.due_date,
                currency: inv.currency,
                subtotal: inv.subtotal == null ? null : Number(inv.subtotal),
                tax: inv.tax == null ? null : Number(inv.tax),
                total: inv.total == null ? null : Number(inv.total),
              }}
              initialLines={lines.map((l) => ({
                sku: l.sku,
                description: l.description,
                quantity: Number(l.quantity),
                unit_price: Number(l.unit_price),
                amount: Number(l.amount),
              }))}
            />
          </div>
        </div>
      ) : (
      <>
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="lg:col-span-2">
          <DocumentPreview url={url} fileName={inv.file_name} />
        </div>

        <div className="space-y-6 lg:col-span-3">
          {/* Flags */}
          <section className="card">
            <header className="flex items-center justify-between border-b border-line px-5 py-3">
              <h2 className="font-medium">Checks</h2>
              <span className="text-xs text-muted">{flags.length} finding(s)</span>
            </header>
            {flags.length === 0 ? (
              <p className="flex items-center gap-2 px-5 py-4 text-sm text-brand-700">
                <CheckCircle2 className="size-4" /> Invoice matches the purchase order.
              </p>
            ) : (
              <ul className="divide-y divide-line">
                {flags.map((f) => (
                  <li key={f.id} className="flex gap-3 px-5 py-3">
                    <span className="mt-0.5">{severityIcon[f.severity]}</span>
                    <div className="flex-1 text-sm">
                      <p>{f.message}</p>
                      {(f.expected || f.actual) && (
                        <p className="mt-1 text-xs text-muted">
                          {f.expected && <>Expected <span className="font-mono text-ink">{f.expected}</span></>}
                          {f.expected && f.actual && " · "}
                          {f.actual && <>Found <span className="font-mono text-ink">{f.actual}</span></>}
                        </p>
                      )}
                    </div>
                    <StatusBadge status={f.severity} />
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Header comparison */}
          <section className="card p-5">
            <h2 className="mb-4 font-medium">Extracted details</h2>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
              <Field label="Supplier" value={inv.supplier_name} compare={(po?.suppliers as unknown as { name: string } | null)?.name} />
              <Field label="PO number" value={inv.po_number} compare={po?.po_number} />
              <Field label="Invoice date" value={date(inv.invoice_date)} />
              <Field label="Due date" value={date(inv.due_date)} />
              <Field label="Subtotal" value={money(inv.subtotal, currency)} compare={po ? money(po.total, currency) : undefined} compareLabel="PO total" />
              <Field label="Tax" value={money(inv.tax, currency)} />
            </dl>
          </section>

          {/* Review */}
          <section className="card p-5">
            <h2 className="mb-3 font-medium">Review decision</h2>
            {decided ? (
              <div className="text-sm">
                <p>
                  <StatusBadge status={inv.status} /> by {reviewer?.full_name ?? "a reviewer"} on {dateTime(inv.reviewed_at)}
                </p>
                {inv.review_note && <p className="mt-2 rounded-lg bg-canvas px-3 py-2 text-muted">“{inv.review_note}”</p>}
              </div>
            ) : canReview(profile) ? (
              <form action={reviewInvoice} className="space-y-3">
                <input type="hidden" name="id" value={inv.id} />
                <textarea name="note" className="input" rows={2} placeholder="Note for the audit trail (optional)" />
                <div className="flex gap-2">
                  <button name="decision" value="approved" className="btn-primary">
                    Approve for payment
                  </button>
                  <button name="decision" value="rejected" className="btn-secondary text-red-700">
                    Reject
                  </button>
                </div>
              </form>
            ) : (
              <p className="text-sm text-muted">Only reviewers and admins can approve or reject invoices.</p>
            )}
          </section>
        </div>
      </div>

      {/* Line comparison */}
      <section className="card mt-6 overflow-hidden">
        <header className="border-b border-line px-5 py-3">
          <h2 className="font-medium">Line items: invoice vs purchase order</h2>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="border-b border-line bg-canvas/50">
              <tr>
                <th className="th">Item</th>
                <th className="th text-right">Inv. qty</th>
                <th className="th text-right">PO qty</th>
                <th className="th text-right">Inv. price</th>
                <th className="th text-right">PO price</th>
                <th className="th text-right">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lines.map((l) => {
                const p = findPoLine({ ...l, quantity: Number(l.quantity), unit_price: Number(l.unit_price) }, poLines);
                const qtyBad = p && Number(l.quantity) !== p.quantity;
                const priceBad = p && Math.abs(Number(l.unit_price) - p.unit_price) / (p.unit_price || 1) > 0.01;
                return (
                  <tr key={l.id} className={!p ? "bg-red-50/60" : ""}>
                    <td className="td">
                      <div>{l.description}</div>
                      <div className="font-mono text-xs text-muted">{l.sku ?? "no SKU"}{!p && " · not on PO"}</div>
                    </td>
                    <td className={`td text-right tabular-nums ${qtyBad ? "font-semibold text-amber-700" : ""}`}>{Number(l.quantity)}</td>
                    <td className="td text-right text-muted tabular-nums">{p ? p.quantity : "—"}</td>
                    <td className={`td text-right tabular-nums ${priceBad ? "font-semibold text-red-700" : ""}`}>
                      {money(l.unit_price, currency)}
                    </td>
                    <td className="td text-right text-muted tabular-nums">{p ? money(p.unit_price, currency) : "—"}</td>
                    <td className="td text-right tabular-nums">{money(l.amount, currency)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      </>
      )}

      {/* Audit trail */}
      <section className="card mt-6 p-5">
        <h2 className="mb-3 font-medium">History</h2>
        <ol className="space-y-2 text-sm">
          {(history ?? []).map((h) => (
            <li key={h.id} className="flex gap-3">
              <span className="w-32 shrink-0 text-muted">{dateTime(h.created_at)}</span>
              <span>
                <span className="font-medium">{(h.profiles as unknown as { full_name: string } | null)?.full_name ?? "System"}</span>{" "}
                {h.action} this invoice
              </span>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

function Field({
  label,
  value,
  compare,
  compareLabel = "PO",
}: {
  label: string;
  value: string | null | undefined;
  compare?: string | null;
  compareLabel?: string;
}) {
  const mismatch = compare != null && value != null && compare.toLowerCase() !== value.toLowerCase();
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={`mt-0.5 font-medium ${mismatch ? "text-amber-700" : ""}`}>{value ?? "—"}</dd>
      {compare != null && (
        <dd className="text-xs text-muted">
          {compareLabel}: {compare}
        </dd>
      )}
    </div>
  );
}
