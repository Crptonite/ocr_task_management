"use client";

import { useState, useTransition } from "react";
import { Plus, Trash2 } from "lucide-react";
import { money } from "@/lib/format";
import { createPurchaseOrder, type NewPoInput } from "./actions";

type Line = NewPoInput["lines"][number];
const blankLine = (): Line => ({ sku: "", description: "", quantity: 1, unit_price: 0 });

export function NewPoForm({ suppliers }: { suppliers: string[] }) {
  const [open, setOpen] = useState(false);
  const [poNumber, setPoNumber] = useState("");
  const [supplier, setSupplier] = useState("");
  const [orderDate, setOrderDate] = useState(new Date().toISOString().slice(0, 10));
  const [currency, setCurrency] = useState("SGD");
  const [lines, setLines] = useState<Line[]>([blankLine()]);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const total = lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);

  const setL = (i: number, patch: Partial<Line>) => setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  function reset() {
    setPoNumber("");
    setSupplier("");
    setLines([blankLine()]);
    setError(null);
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    startTransition(async () => {
      const res = await createPurchaseOrder({ po_number: poNumber, supplier_name: supplier, order_date: orderDate, currency, lines });
      if (res.error) {
        setError(res.error);
        return;
      }
      reset();
      setOpen(false);
    });
  }

  if (!open) {
    return (
      <button className="btn-primary" onClick={() => setOpen(true)}>
        <Plus className="size-4" /> New purchase order
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="card mb-6 w-full p-5">
      <h2 className="mb-4 font-medium">New purchase order</h2>
      <div className="grid gap-4 sm:grid-cols-4">
        <label>
          <span className="label">PO number</span>
          <input className="input font-mono" value={poNumber} onChange={(e) => setPoNumber(e.target.value)} placeholder="PO-2026-0105" required />
        </label>
        <label className="sm:col-span-2">
          <span className="label">Supplier</span>
          <input
            className="input"
            list="supplier-names"
            value={supplier}
            onChange={(e) => setSupplier(e.target.value)}
            placeholder="Pick an existing supplier or type a new one"
            required
          />
          <datalist id="supplier-names">
            {suppliers.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </label>
        <label>
          <span className="label">Order date</span>
          <input className="input" type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
        </label>
      </div>

      <div className="mt-5 overflow-x-auto rounded-lg border border-line">
        <table className="w-full min-w-[600px]">
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
                  <input className="input" value={l.description} onChange={(e) => setL(i, { description: e.target.value })} required={i === 0} />
                </td>
                <td className="px-2 py-2">
                  <input className="input text-right" type="number" min="0" value={l.quantity} onChange={(e) => setL(i, { quantity: Number(e.target.value) })} />
                </td>
                <td className="px-2 py-2">
                  <input className="input text-right" type="number" min="0" step="0.01" value={l.unit_price} onChange={(e) => setL(i, { unit_price: Number(e.target.value) })} />
                </td>
                <td className="td text-right tabular-nums">{money(l.quantity * l.unit_price, currency)}</td>
                <td className="px-2">
                  {lines.length > 1 && (
                    <button
                      type="button"
                      className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"
                      title="Remove line"
                      onClick={() => setLines((ls) => ls.filter((_, idx) => idx !== i))}
                    >
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="btn-secondary" onClick={() => setLines((ls) => [...ls, blankLine()])}>
          <Plus className="size-4" /> Add line
        </button>
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm text-muted">
            Total <span className="font-medium text-ink tabular-nums">{money(total, currency)}</span>
          </span>
          <input className="input w-20" value={currency} onChange={(e) => setCurrency(e.target.value)} aria-label="Currency" />
          {error && <span className="text-sm text-red-700">{error}</span>}
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              reset();
              setOpen(false);
            }}
          >
            Cancel
          </button>
          <button className="btn-primary" disabled={pending}>
            {pending ? "Saving…" : "Create PO"}
          </button>
        </div>
      </div>
    </form>
  );
}
