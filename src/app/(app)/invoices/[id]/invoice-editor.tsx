"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus, Trash2 } from "lucide-react";
import { money } from "@/lib/format";
import { saveInvoice, type InvoiceHeaderInput, type InvoiceLineInput } from "../actions";

export function InvoiceEditor({
  id,
  initialHeader,
  initialLines,
  poNumbers,
}: {
  id: string;
  initialHeader: InvoiceHeaderInput;
  initialLines: InvoiceLineInput[];
  poNumbers: string[];
}) {
  const router = useRouter();
  const [header, setHeader] = useState(initialHeader);
  const [lines, setLines] = useState(initialLines);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const currency = header.currency || "SGD";
  const lineTotal = lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);

  const setH = <K extends keyof InvoiceHeaderInput>(key: K, value: InvoiceHeaderInput[K]) =>
    setHeader((h) => ({ ...h, [key]: value }));
  const setL = (i: number, patch: Partial<InvoiceLineInput>) =>
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  const num = (v: string) => (v === "" ? null : Number(v));

  function save() {
    setError(null);
    startTransition(async () => {
      const res = await saveInvoice(
        id,
        header,
        lines.map((l) => ({ ...l, amount: l.quantity * l.unit_price })),
      );
      if (res.error) {
        setError(res.error);
        return;
      }
      router.push(`/invoices/${id}`);
      router.refresh();
    });
  }

  return (
    <div className="space-y-6">
      <section className="card p-5">
        <h2 className="mb-4 font-medium">Edit invoice details</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Invoice number" value={header.invoice_number} onChange={(v) => setH("invoice_number", v)} />
          <Field label="Supplier" value={header.supplier_name} onChange={(v) => setH("supplier_name", v)} />
          <label className="block">
            <span className="label">PO number</span>
            <input
              className="input font-mono"
              list="po-numbers"
              value={header.po_number ?? ""}
              onChange={(e) => setH("po_number", e.target.value || null)}
            />
            <datalist id="po-numbers">
              {poNumbers.map((p) => (
                <option key={p} value={p} />
              ))}
            </datalist>
          </label>
          <Field label="Invoice date" type="date" value={header.invoice_date} onChange={(v) => setH("invoice_date", v)} />
          <Field label="Due date" type="date" value={header.due_date} onChange={(v) => setH("due_date", v)} />
          <Field label="Currency" value={header.currency} onChange={(v) => setH("currency", v?.toUpperCase() ?? null)} />
          <Field label="Subtotal" type="number" value={header.subtotal?.toString() ?? null} onChange={(v) => setH("subtotal", num(v ?? ""))} />
          <Field label="Tax" type="number" value={header.tax?.toString() ?? null} onChange={(v) => setH("tax", num(v ?? ""))} />
          <Field label="Total" type="number" value={header.total?.toString() ?? null} onChange={(v) => setH("total", num(v ?? ""))} />
        </div>
        <button
          type="button"
          className="mt-3 text-xs text-brand-600 hover:underline"
          onClick={() => {
            const subtotal = Math.round(lineTotal * 100) / 100;
            const tax = Math.round(subtotal * 0.09 * 100) / 100;
            setHeader((h) => ({ ...h, subtotal, tax, total: Math.round((subtotal + tax) * 100) / 100 }));
          }}
        >
          Fill totals from lines (+9% GST)
        </button>
      </section>

      <section className="card overflow-hidden">
        <header className="flex items-center justify-between border-b border-line px-5 py-3">
          <h2 className="font-medium">Line items</h2>
          <span className="text-sm text-muted">
            Line total <span className="font-medium text-ink tabular-nums">{money(lineTotal, currency)}</span>
          </span>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead className="border-b border-line bg-canvas/50">
              <tr>
                <th className="th w-36">SKU</th>
                <th className="th">Description</th>
                <th className="th w-24 text-right">Qty</th>
                <th className="th w-28 text-right">Unit price</th>
                <th className="th w-28 text-right">Amount</th>
                <th className="th w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lines.map((l, i) => (
                <tr key={i}>
                  <td className="px-2 py-2">
                    <input className="input font-mono text-xs" value={l.sku ?? ""} onChange={(e) => setL(i, { sku: e.target.value })} />
                  </td>
                  <td className="px-2 py-2">
                    <input className="input" value={l.description} onChange={(e) => setL(i, { description: e.target.value })} />
                  </td>
                  <td className="px-2 py-2">
                    <input className="input text-right" type="number" value={l.quantity} onChange={(e) => setL(i, { quantity: Number(e.target.value) })} />
                  </td>
                  <td className="px-2 py-2">
                    <input className="input text-right" type="number" step="0.01" value={l.unit_price} onChange={(e) => setL(i, { unit_price: Number(e.target.value) })} />
                  </td>
                  <td className="td text-right tabular-nums">{money(l.quantity * l.unit_price, currency)}</td>
                  <td className="px-2">
                    <button
                      className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"
                      title="Remove line"
                      onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3">
          <button
            className="btn-secondary"
            onClick={() => setLines((ls) => [...ls, { sku: "", description: "", quantity: 1, unit_price: 0, amount: 0 }])}
          >
            <Plus className="size-4" /> Add line
          </button>
          <div className="flex items-center gap-2">
            {error && <span className="text-sm text-red-700">{error}</span>}
            <Link href={`/invoices/${id}`} className="btn-secondary">
              Cancel
            </Link>
            <button className="btn-primary" disabled={pending} onClick={save}>
              {pending ? "Re-checking…" : "Save & re-check"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        className="input"
        type={type}
        step={type === "number" ? "0.01" : undefined}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
      />
    </label>
  );
}
