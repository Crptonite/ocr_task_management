"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Plus, Trash2 } from "lucide-react";
import { money } from "@/lib/format";
import { saveOrder } from "../actions";

type Header = {
  order_type: "purchase" | "sales";
  order_number: string | null;
  counterparty: string | null;
  order_date: string | null;
  delivery_date: string | null;
  currency: string | null;
  total: number | null;
};
type Line = { sku: string | null; description: string; quantity: number; unit_price: number; amount: number; issues: string[] };

export function OrderEditor({
  id,
  locked,
  initialHeader,
  initialLines,
  initialIssues,
}: {
  id: string;
  locked: boolean;
  initialHeader: Header;
  initialLines: Line[];
  initialIssues: string[];
}) {
  const router = useRouter();
  const [header, setHeader] = useState(initialHeader);
  const [lines, setLines] = useState(initialLines);
  const [issues, setIssues] = useState(initialIssues);
  const [dirty, setDirty] = useState(false);
  const [pending, startTransition] = useTransition();
  const currency = header.currency ?? "SGD";
  const lineTotal = lines.reduce((s, l) => s + l.quantity * l.unit_price, 0);

  function setH<K extends keyof Header>(key: K, value: Header[K]) {
    setHeader((h) => ({ ...h, [key]: value }));
    setDirty(true);
  }
  function setL(i: number, patch: Partial<Line>) {
    setLines((ls) => ls.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
    setDirty(true);
  }

  function save() {
    startTransition(async () => {
      const result = await saveOrder(
        id,
        header,
        lines.map((l) => ({
          sku: l.sku,
          description: l.description,
          quantity: l.quantity,
          unit_price: l.unit_price,
          amount: l.quantity * l.unit_price,
        })),
      );
      if ("error" in result && result.error) {
        alert(result.error);
        return;
      }
      setIssues(result.issues ?? []);
      // Server drops lines with an empty description; mirror that, then attach fresh per-line issues.
      setLines((ls) =>
        ls.filter((l) => l.description.trim()).map((l, i) => ({ ...l, issues: result.lineIssues?.[i] ?? [] })),
      );
      setDirty(false);
      router.refresh();
    });
  }

  return (
    <div className="space-y-6">
      <section
        className={`card flex gap-3 p-4 text-sm ${issues.length ? "border-amber-200 bg-amber-50/60" : "border-brand-100 bg-brand-50/60"}`}
      >
        {issues.length ? (
          <>
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <div>
              <p className="font-medium text-amber-900">Fix these before approval</p>
              <ul className="mt-1 list-disc pl-5 text-amber-900/80">
                {issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            </div>
          </>
        ) : (
          <>
            <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-600" />
            <p className="text-brand-800">All validation checks passed.</p>
          </>
        )}
      </section>

      <section className="card p-5">
        <h2 className="mb-4 font-medium">Order details</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className="label">Order type</span>
            <select
              className="input"
              value={header.order_type}
              disabled={locked}
              onChange={(e) => setH("order_type", e.target.value as Header["order_type"])}
            >
              <option value="sales">Sales order (from a customer)</option>
              <option value="purchase">Purchase order (to a supplier)</option>
            </select>
          </label>
          <TextField label="Order number" value={header.order_number} onChange={(v) => setH("order_number", v)} disabled={locked} />
          <TextField label="Customer / supplier" value={header.counterparty} onChange={(v) => setH("counterparty", v)} disabled={locked} />
          <TextField label="Order date" type="date" value={header.order_date} onChange={(v) => setH("order_date", v)} disabled={locked} />
          <TextField label="Delivery date" type="date" value={header.delivery_date} onChange={(v) => setH("delivery_date", v)} disabled={locked} />
          <TextField label="Currency" value={header.currency} onChange={(v) => setH("currency", v?.toUpperCase() ?? null)} disabled={locked} />
          <TextField
            label="Document total"
            type="number"
            value={header.total == null ? null : String(header.total)}
            onChange={(v) => setH("total", v === null || v === "" ? null : Number(v))}
            disabled={locked}
          />
        </div>
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
                <th className="th w-8">#</th>
                <th className="th w-36">SKU</th>
                <th className="th">Description</th>
                <th className="th w-20 text-right">Qty</th>
                <th className="th w-28 text-right">Unit price</th>
                <th className="th w-28 text-right">Amount</th>
                {!locked && <th className="th w-8" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {lines.map((l, i) => (
                <tr key={i} className={l.issues.length && !dirty ? "bg-amber-50/50" : ""}>
                  <td className="td text-muted">{i + 1}</td>
                  <td className="px-2 py-2">
                    <input className="input font-mono text-xs" value={l.sku ?? ""} disabled={locked} onChange={(e) => setL(i, { sku: e.target.value })} />
                  </td>
                  <td className="px-2 py-2">
                    <input className="input" value={l.description} disabled={locked} onChange={(e) => setL(i, { description: e.target.value })} />
                    {l.issues.length > 0 && !dirty && <p className="mt-1 text-xs text-amber-700">{l.issues.join(" · ")}</p>}
                  </td>
                  <td className="px-2 py-2">
                    <input className="input text-right" type="number" value={l.quantity} disabled={locked} onChange={(e) => setL(i, { quantity: Number(e.target.value) })} />
                  </td>
                  <td className="px-2 py-2">
                    <input className="input text-right" type="number" step="0.01" value={l.unit_price} disabled={locked} onChange={(e) => setL(i, { unit_price: Number(e.target.value) })} />
                  </td>
                  <td className="td text-right tabular-nums">{money(l.quantity * l.unit_price, currency)}</td>
                  {!locked && (
                    <td className="px-2">
                      <button
                        className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"
                        title="Remove line"
                        onClick={() => {
                          setLines((ls) => ls.filter((_, idx) => idx !== i));
                          setDirty(true);
                        }}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!locked && (
          <div className="flex items-center justify-between border-t border-line px-5 py-3">
            <button
              className="btn-secondary"
              onClick={() => {
                setLines((ls) => [...ls, { sku: "", description: "", quantity: 1, unit_price: 0, amount: 0, issues: [] }]);
                setDirty(true);
              }}
            >
              <Plus className="size-4" /> Add line
            </button>
            <button className="btn-primary" disabled={!dirty || pending} onClick={save}>
              {pending ? "Validating…" : "Save & re-validate"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  type = "text",
  disabled,
}: {
  label: string;
  value: string | null;
  onChange: (v: string | null) => void;
  type?: string;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input
        className={`input ${!value ? "border-amber-300" : ""}`}
        type={type}
        step={type === "number" ? "0.01" : undefined}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
      />
    </label>
  );
}
