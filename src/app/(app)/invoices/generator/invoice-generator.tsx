"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Download, FileSearch, Loader2, Plus, Trash2 } from "lucide-react";
import { createClient } from "@/lib/supabase/client";
import { buildInvoicePdf, invoiceTotals, type InvoiceDoc } from "@/lib/invoice-pdf";
import { money } from "@/lib/format";
import { processInvoice } from "../actions";

export type PoOption = {
  po_number: string;
  currency: string;
  supplier_name: string;
  supplier_email: string;
  lines: InvoiceDoc["lines"];
};

type Line = InvoiceDoc["lines"][number];

const today = () => new Date().toISOString().slice(0, 10);
const plusDays = (d: string, n: number) => new Date(new Date(d).getTime() + n * 86400000).toISOString().slice(0, 10);
const randomInvoiceNo = () => `INV-${new Date().getFullYear()}-${Math.floor(1000 + Math.random() * 9000)}`;

const SCENARIOS = [
  { key: "exact", label: "Exact match", hint: "Should auto-match" },
  { key: "price", label: "Price +8%", hint: "First line overpriced" },
  { key: "qty", label: "Over-billed qty", hint: "+10 units on last line" },
  { key: "extra", label: "Item not on PO", hint: "Adds a delivery charge" },
  { key: "partial", label: "Partial delivery", hint: "Last line left off" },
] as const;
type Scenario = (typeof SCENARIOS)[number]["key"];

function applyScenario(base: Line[], scenario: Scenario): Line[] {
  const lines = base.map((l) => ({ ...l }));
  if (lines.length === 0) return lines;
  const last = lines.length - 1;
  switch (scenario) {
    case "price":
      lines[0].unit_price = Math.round(lines[0].unit_price * 1.08 * 100) / 100;
      return lines;
    case "qty":
      lines[last].quantity += 10;
      return lines;
    case "extra":
      return [...lines, { sku: "SVC-DEL", description: "Express delivery surcharge", quantity: 1, unit_price: 180 }];
    case "partial":
      return lines.length > 1 ? lines.slice(0, -1) : lines;
    default:
      return lines;
  }
}

export function InvoiceGenerator({ pos }: { pos: PoOption[] }) {
  const router = useRouter();
  const [doc, setDoc] = useState<InvoiceDoc>(() => ({
    supplier: { name: "", address: "Singapore", email: "", reg_no: "" },
    bill_to: { name: "OpsPilot Furniture Pte Ltd", address: "12 Woodlands Loop\nSingapore 738283" },
    invoice_number: randomInvoiceNo(),
    invoice_date: today(),
    due_date: plusDays(today(), 30),
    po_number: "",
    currency: "SGD",
    tax_rate: 9,
    lines: [{ sku: "", description: "", quantity: 1, unit_price: 0 }],
    notes: "Payment terms: 30 days. Please quote the invoice number with your payment.",
  }));
  const [scenario, setScenario] = useState<Scenario>("exact");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, startChecking] = useTransition();

  const totals = invoiceTotals(doc);
  const selectedPo = pos.find((p) => p.po_number === doc.po_number);

  // Re-render the PDF preview shortly after the user stops typing.
  useEffect(() => {
    let url: string | null = null;
    let cancelled = false;
    const timer = setTimeout(async () => {
      const bytes = await buildInvoicePdf(doc);
      if (cancelled) return;
      url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
      setPreviewUrl(url);
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      if (url) URL.revokeObjectURL(url);
    };
  }, [doc]);

  const set = (patch: Partial<InvoiceDoc>) => setDoc((d) => ({ ...d, ...patch }));
  const setSupplier = (patch: Partial<InvoiceDoc["supplier"]>) => setDoc((d) => ({ ...d, supplier: { ...d.supplier, ...patch } }));
  const setLine = (i: number, patch: Partial<Line>) =>
    setDoc((d) => ({ ...d, lines: d.lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l)) }));

  function pickPo(poNumber: string) {
    const po = pos.find((p) => p.po_number === poNumber);
    if (!po) {
      set({ po_number: poNumber });
      return;
    }
    setDoc((d) => ({
      ...d,
      po_number: po.po_number,
      currency: po.currency,
      supplier: { ...d.supplier, name: po.supplier_name, email: po.supplier_email },
      lines: applyScenario(po.lines, scenario),
    }));
  }

  function pickScenario(s: Scenario) {
    setScenario(s);
    if (selectedPo) set({ lines: applyScenario(selectedPo.lines, s) });
  }

  const fileName = `${doc.invoice_number || "invoice"}.pdf`.replace(/[^\w.-]/g, "_");

  async function download() {
    const bytes = await buildInvoicePdf(doc);
    const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function sendToChecker() {
    setError(null);
    startChecking(async () => {
      const bytes = await buildInvoicePdf(doc);
      const path = `invoices/${crypto.randomUUID()}-${fileName}`;
      const { error: uploadError } = await createClient()
        .storage.from("documents")
        .upload(path, new Blob([bytes as BlobPart], { type: "application/pdf" }), { contentType: "application/pdf" });
      if (uploadError) {
        setError(uploadError.message);
        return;
      }
      const res = await processInvoice(path, "application/pdf", fileName);
      if (res.error || !res.id) {
        setError(res.error ?? "Processing failed.");
        return;
      }
      router.push(`/invoices/${res.id}`);
    });
  }

  const valid = doc.supplier.name.trim() && doc.invoice_number.trim() && doc.lines.some((l) => l.description.trim());

  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <div className="space-y-6">
        <section className="card p-5">
          <h2 className="mb-1 font-medium">Start from a purchase order</h2>
          <p className="mb-3 text-sm text-muted">Fills in the supplier and line items. Pick a scenario to test the checker.</p>
          <select className="input" value={selectedPo ? doc.po_number : ""} onChange={(e) => pickPo(e.target.value)}>
            <option value="">— No PO (blank invoice) —</option>
            {pos.map((p) => (
              <option key={p.po_number} value={p.po_number}>
                {p.po_number} · {p.supplier_name}
              </option>
            ))}
          </select>
          {selectedPo && (
            <div className="mt-3 flex flex-wrap gap-2">
              {SCENARIOS.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  title={s.hint}
                  onClick={() => pickScenario(s.key)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    scenario === s.key ? "border-brand-600 bg-brand-50 font-medium text-brand-700" : "border-line text-muted hover:text-ink"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="card grid gap-4 p-5 sm:grid-cols-2">
          <h2 className="font-medium sm:col-span-2">From (supplier)</h2>
          <Input label="Supplier name" value={doc.supplier.name} onChange={(v) => setSupplier({ name: v })} />
          <Input label="Email" value={doc.supplier.email} onChange={(v) => setSupplier({ email: v })} />
          <TextArea label="Address" value={doc.supplier.address} onChange={(v) => setSupplier({ address: v })} />
          <Input label="Company reg. no." value={doc.supplier.reg_no} onChange={(v) => setSupplier({ reg_no: v })} />

          <h2 className="mt-2 font-medium sm:col-span-2">Bill to</h2>
          <Input label="Company" value={doc.bill_to.name} onChange={(v) => set({ bill_to: { ...doc.bill_to, name: v } })} />
          <TextArea label="Address" value={doc.bill_to.address} onChange={(v) => set({ bill_to: { ...doc.bill_to, address: v } })} />
        </section>

        <section className="card grid gap-4 p-5 sm:grid-cols-3">
          <h2 className="font-medium sm:col-span-3">Invoice details</h2>
          <Input label="Invoice number" value={doc.invoice_number} onChange={(v) => set({ invoice_number: v })} mono />
          <Input label="PO number" value={doc.po_number} onChange={(v) => set({ po_number: v })} mono />
          <Input label="Currency" value={doc.currency} onChange={(v) => set({ currency: v.toUpperCase() })} />
          <Input label="Invoice date" type="date" value={doc.invoice_date} onChange={(v) => set({ invoice_date: v })} />
          <Input label="Due date" type="date" value={doc.due_date} onChange={(v) => set({ due_date: v })} />
          <Input label="GST %" type="number" value={String(doc.tax_rate)} onChange={(v) => set({ tax_rate: Number(v) || 0 })} />
        </section>

        <section className="card overflow-hidden">
          <header className="border-b border-line px-5 py-3">
            <h2 className="font-medium">Line items</h2>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead className="border-b border-line bg-canvas/50">
                <tr>
                  <th className="th w-32">SKU</th>
                  <th className="th">Description</th>
                  <th className="th w-20 text-right">Qty</th>
                  <th className="th w-28 text-right">Unit price</th>
                  <th className="th w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {doc.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="px-2 py-2">
                      <input className="input font-mono text-xs" value={l.sku} onChange={(e) => setLine(i, { sku: e.target.value })} />
                    </td>
                    <td className="px-2 py-2">
                      <input className="input" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} />
                    </td>
                    <td className="px-2 py-2">
                      <input className="input text-right" type="number" min="0" value={l.quantity} onChange={(e) => setLine(i, { quantity: Number(e.target.value) })} />
                    </td>
                    <td className="px-2 py-2">
                      <input className="input text-right" type="number" min="0" step="0.01" value={l.unit_price} onChange={(e) => setLine(i, { unit_price: Number(e.target.value) })} />
                    </td>
                    <td className="px-2">
                      <button
                        type="button"
                        className="rounded p-1 text-muted hover:bg-red-50 hover:text-red-600"
                        title="Remove line"
                        onClick={() => set({ lines: doc.lines.filter((_, idx) => idx !== i) })}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-5 py-3 text-sm">
            <button
              type="button"
              className="btn-secondary"
              onClick={() => set({ lines: [...doc.lines, { sku: "", description: "", quantity: 1, unit_price: 0 }] })}
            >
              <Plus className="size-4" /> Add line
            </button>
            <div className="text-right text-muted">
              Subtotal {money(totals.subtotal, doc.currency || "SGD")} · GST {money(totals.tax, doc.currency || "SGD")} ·{" "}
              <span className="font-semibold text-ink">Total {money(totals.total, doc.currency || "SGD")}</span>
            </div>
          </div>
        </section>

        <section className="card p-5">
          <TextArea label="Notes / payment terms" value={doc.notes} onChange={(v) => set({ notes: v })} />
        </section>
      </div>

      <div className="space-y-4 xl:sticky xl:top-6 xl:self-start">
        <div className="flex flex-wrap gap-2">
          <button className="btn-primary" onClick={download} disabled={!valid}>
            <Download className="size-4" /> Download PDF
          </button>
          <button className="btn-secondary" onClick={sendToChecker} disabled={!valid || checking}>
            {checking ? <Loader2 className="size-4 animate-spin" /> : <FileSearch className="size-4" />}
            {checking ? "Checking…" : "Send to invoice checker"}
          </button>
          {!valid && <span className="self-center text-xs text-muted">Add a supplier, invoice number and one line to continue.</span>}
        </div>
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="card overflow-hidden bg-stone-100">
          {previewUrl ? (
            <iframe src={previewUrl} title="Invoice PDF preview" className="h-[780px] w-full" />
          ) : (
            <p className="p-10 text-center text-sm text-muted">Rendering preview…</p>
          )}
        </div>
      </div>
    </div>
  );
}

function Input({
  label,
  value,
  onChange,
  type = "text",
  mono,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  mono?: boolean;
}) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <input className={`input ${mono ? "font-mono" : ""}`} type={type} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <textarea className="input" rows={3} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}
