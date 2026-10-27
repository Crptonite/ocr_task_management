"use client";

import { useActionState, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { Plus, Search, Trash2 } from "lucide-react";
import { ConfirmButton } from "@/components/confirm-button";
import { createProduct, deleteProduct, updateProduct } from "./actions";

export type Product = { sku: string; name: string; category: string; unit_price: number; active: boolean };

export function Catalogue({ products }: { products: Product[] }) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [state, formAction, adding] = useActionState(createProduct, null);
  const formRef = useRef<HTMLFormElement>(null);
  const [, startTransition] = useTransition();

  useEffect(() => {
    if (state?.ok) formRef.current?.reset();
  }, [state]);

  const categories = useMemo(() => [...new Set(products.map((p) => p.category))].sort(), [products]);
  const counts = useMemo(() => {
    const m = new Map<string, number>();
    for (const p of products) m.set(p.category, (m.get(p.category) ?? 0) + 1);
    return m;
  }, [products]);

  const q = query.trim().toLowerCase();
  const visible = products.filter(
    (p) =>
      (category === "All" || p.category === category) &&
      (!q || p.sku.toLowerCase().includes(q) || p.name.toLowerCase().includes(q)),
  );
  const grouped = categories
    .map((c) => ({ category: c, items: visible.filter((p) => p.category === c) }))
    .filter((g) => g.items.length > 0);

  const save = (sku: string, patch: Parameters<typeof updateProduct>[1]) => startTransition(() => void updateProduct(sku, patch));

  return (
    <div className="space-y-6">
      <form ref={formRef} action={formAction} className="card grid gap-3 p-5 sm:grid-cols-[150px_1fr_200px_130px_auto] sm:items-end">
        <label>
          <span className="label">SKU</span>
          <input name="sku" className="input font-mono uppercase" placeholder="MAT-HYB-Q" required />
        </label>
        <label>
          <span className="label">Product name</span>
          <input name="name" className="input" placeholder="Hybrid mattress, queen" required />
        </label>
        <label>
          <span className="label">Category</span>
          <input name="category" className="input" list="product-categories" placeholder="Pick or type a new one" required />
          <datalist id="product-categories">
            {categories.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </label>
        <label>
          <span className="label">List price</span>
          <input name="unit_price" type="number" min="0" step="0.01" className="input text-right" required />
        </label>
        <button className="btn-primary" disabled={adding}>
          <Plus className="size-4" /> Add product
        </button>
        {state?.error && <p className="text-sm text-red-700 sm:col-span-5">{state.error}</p>}
      </form>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" />
          <input className="input pl-9" placeholder="Search SKU or name" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {["All", ...categories].map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`rounded-full border px-3 py-1 text-xs ${
              category === c ? "border-brand-600 bg-brand-50 font-medium text-brand-700" : "border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {c} <span className="opacity-60">{c === "All" ? products.length : counts.get(c)}</span>
          </button>
        ))}
      </div>

      {grouped.length === 0 && <p className="card px-5 py-10 text-center text-sm text-muted">No products match.</p>}

      {grouped.map((g) => (
        <section key={g.category} className="card overflow-hidden">
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <h2 className="font-medium">{g.category}</h2>
            <span className="text-xs text-muted">{g.items.length} product(s)</span>
          </header>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px]">
              <thead className="border-b border-line bg-canvas/50">
                <tr>
                  <th className="th w-40">SKU</th>
                  <th className="th">Name</th>
                  <th className="th w-48">Category</th>
                  <th className="th w-32 text-right">List price</th>
                  <th className="th w-20">Active</th>
                  <th className="th w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {g.items.map((p) => (
                  <tr key={p.sku} className={p.active ? "" : "opacity-50"}>
                    <td className="td font-mono text-xs">{p.sku}</td>
                    <td className="px-2 py-2">
                      <input
                        className="input border-transparent bg-transparent hover:border-line"
                        defaultValue={p.name}
                        aria-label={`Name for ${p.sku}`}
                        onBlur={(e) => e.target.value.trim() && e.target.value !== p.name && save(p.sku, { name: e.target.value.trim() })}
                      />
                    </td>
                    <td className="px-2 py-2">
                      <input
                        className="input border-transparent bg-transparent hover:border-line"
                        list="product-categories"
                        defaultValue={p.category}
                        aria-label={`Category for ${p.sku}`}
                        onBlur={(e) =>
                          e.target.value.trim() && e.target.value !== p.category && save(p.sku, { category: e.target.value.trim() })
                        }
                      />
                    </td>
                    <td className="px-2 py-2">
                      <input
                        className="input border-transparent bg-transparent text-right tabular-nums hover:border-line"
                        type="number"
                        min="0"
                        step="0.01"
                        defaultValue={p.unit_price.toFixed(2)}
                        aria-label={`Price for ${p.sku}`}
                        onBlur={(e) => {
                          const v = Number(e.target.value);
                          if (v >= 0 && v !== p.unit_price) save(p.sku, { unit_price: v });
                        }}
                      />
                    </td>
                    <td className="td">
                      <input
                        type="checkbox"
                        className="accent-brand-600"
                        defaultChecked={p.active}
                        aria-label={`${p.sku} active`}
                        onChange={(e) => save(p.sku, { active: e.target.checked })}
                      />
                    </td>
                    <td className="px-2">
                      <form action={deleteProduct}>
                        <input type="hidden" name="sku" value={p.sku} />
                        <ConfirmButton
                          message={`Delete ${p.sku} from the catalogue? Orders using it will be flagged “SKU not in catalogue”.`}
                          className="rounded-md p-1.5 text-muted hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 className="size-4" aria-label={`Delete ${p.sku}`} />
                        </ConfirmButton>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
