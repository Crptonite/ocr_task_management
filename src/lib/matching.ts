// Pure comparison rules: invoice vs purchase order (+ duplicate check).
// Kept free of I/O so the rules are easy to read, test and explain in a demo.

export type Severity = "high" | "medium" | "low";

export type Flag = {
  code: string;
  severity: Severity;
  message: string;
  expected?: string | null;
  actual?: string | null;
};

type Line = { sku: string | null; description: string; quantity: number; unit_price: number; amount?: number };

export type InvoiceForMatch = {
  invoice_number: string | null;
  supplier_name: string | null;
  po_number: string | null;
  subtotal: number | null;
  tax: number | null;
  total: number | null;
  confidence: number;
  lines: Line[];
};

export type PoForMatch = {
  po_number: string;
  supplier_name: string | null;
  lines: Line[];
} | null;

const PRICE_TOLERANCE = 0.01; // 1%
const MONEY_TOLERANCE = 0.05; // 5 cents rounding

const money = (n: number | null | undefined) => (n == null ? "—" : n.toFixed(2));
const norm = (s: string | null | undefined) => (s ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");

/** Match an invoice line to a PO line by SKU, then by description. */
export function findPoLine(line: Line, poLines: Line[]): Line | undefined {
  if (line.sku) {
    const bySku = poLines.find((p) => p.sku && norm(p.sku) === norm(line.sku));
    if (bySku) return bySku;
  }
  const d = norm(line.description);
  return poLines.find((p) => {
    const pd = norm(p.description);
    return pd === d || (d.length > 8 && (pd.includes(d) || d.includes(pd)));
  });
}

export function compareInvoice(
  invoice: InvoiceForMatch,
  po: PoForMatch,
  isDuplicate: boolean,
): Flag[] {
  const flags: Flag[] = [];

  if (invoice.confidence < 0.75) {
    flags.push({
      code: "LOW_CONFIDENCE",
      severity: "medium",
      message: "The document was hard to read. Double-check the extracted values.",
      actual: `${Math.round(invoice.confidence * 100)}% confidence`,
    });
  }

  if (isDuplicate) {
    flags.push({
      code: "DUPLICATE_INVOICE",
      severity: "high",
      message: "An invoice with this number from this supplier has already been processed.",
      actual: invoice.invoice_number,
    });
  }

  // Arithmetic checks on the invoice itself.
  for (const line of invoice.lines) {
    const expected = line.quantity * line.unit_price;
    if (line.amount != null && Math.abs(expected - line.amount) > MONEY_TOLERANCE) {
      flags.push({
        code: "LINE_ARITHMETIC",
        severity: "medium",
        message: `Line "${line.description}" does not add up (qty × unit price).`,
        expected: money(expected),
        actual: money(line.amount),
      });
    }
  }
  const lineSum = invoice.lines.reduce((s, l) => s + (l.amount ?? l.quantity * l.unit_price), 0);
  if (invoice.subtotal != null && Math.abs(lineSum - invoice.subtotal) > MONEY_TOLERANCE) {
    flags.push({
      code: "SUBTOTAL_MISMATCH",
      severity: "medium",
      message: "Invoice subtotal does not equal the sum of its lines.",
      expected: money(lineSum),
      actual: money(invoice.subtotal),
    });
  }
  if (invoice.total != null && invoice.subtotal != null) {
    const expectedTotal = invoice.subtotal + (invoice.tax ?? 0);
    if (Math.abs(expectedTotal - invoice.total) > MONEY_TOLERANCE) {
      flags.push({
        code: "TOTAL_MISMATCH",
        severity: "medium",
        message: "Invoice total does not equal subtotal + tax.",
        expected: money(expectedTotal),
        actual: money(invoice.total),
      });
    }
  }

  if (!po) {
    flags.push({
      code: "PO_NOT_FOUND",
      severity: "high",
      message: invoice.po_number
        ? "The referenced purchase order does not exist in our records."
        : "The invoice does not reference a purchase order.",
      actual: invoice.po_number ?? "none",
    });
    return flags;
  }

  if (po.supplier_name && invoice.supplier_name && norm(po.supplier_name) !== norm(invoice.supplier_name)) {
    const a = norm(po.supplier_name);
    const b = norm(invoice.supplier_name);
    if (!a.includes(b) && !b.includes(a)) {
      flags.push({
        code: "SUPPLIER_MISMATCH",
        severity: "high",
        message: "The supplier on the invoice is not the supplier on the purchase order.",
        expected: po.supplier_name,
        actual: invoice.supplier_name,
      });
    }
  }

  const matched = new Set<Line>();
  for (const line of invoice.lines) {
    const poLine = findPoLine(line, po.lines);
    if (!poLine) {
      flags.push({
        code: "LINE_NOT_ON_PO",
        severity: "high",
        message: `"${line.description}" was invoiced but is not on the purchase order.`,
        actual: `${line.quantity} × ${money(line.unit_price)}`,
      });
      continue;
    }
    matched.add(poLine);
    if (poLine.unit_price > 0 && Math.abs(line.unit_price - poLine.unit_price) / poLine.unit_price > PRICE_TOLERANCE) {
      const pct = ((line.unit_price - poLine.unit_price) / poLine.unit_price) * 100;
      flags.push({
        code: "PRICE_MISMATCH",
        severity: Math.abs(pct) >= 5 ? "high" : "medium",
        message: `Unit price for "${poLine.description}" differs from the PO by ${pct > 0 ? "+" : ""}${pct.toFixed(1)}%.`,
        expected: money(poLine.unit_price),
        actual: money(line.unit_price),
      });
    }
    if (line.quantity > poLine.quantity) {
      flags.push({
        code: "QTY_OVER_PO",
        severity: "high",
        message: `More "${poLine.description}" invoiced than ordered.`,
        expected: String(poLine.quantity),
        actual: String(line.quantity),
      });
    } else if (line.quantity < poLine.quantity) {
      flags.push({
        code: "PARTIAL_DELIVERY",
        severity: "low",
        message: `Fewer "${poLine.description}" invoiced than ordered (possible partial delivery).`,
        expected: String(poLine.quantity),
        actual: String(line.quantity),
      });
    }
  }

  for (const poLine of po.lines) {
    if (!matched.has(poLine)) {
      flags.push({
        code: "PO_LINE_NOT_INVOICED",
        severity: "low",
        message: `"${poLine.description}" is on the PO but not on this invoice.`,
        expected: `${poLine.quantity} × ${money(poLine.unit_price)}`,
      });
    }
  }

  return flags;
}

/** An invoice is auto-matched only when nothing above "low" was found. */
export function statusFromFlags(flags: Flag[]): "matched" | "flagged" {
  return flags.some((f) => f.severity !== "low") ? "flagged" : "matched";
}
