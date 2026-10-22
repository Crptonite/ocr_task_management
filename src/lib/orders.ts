// Validation rules for extracted purchase/sales orders before ERP export.

export type OrderLineInput = {
  sku: string | null;
  description: string;
  quantity: number;
  unit_price: number;
  amount: number;
};

export type OrderHeaderInput = {
  order_number: string | null;
  counterparty: string | null;
  order_date: string | null;
  delivery_date: string | null;
  total: number | null;
};

export type CatalogItem = { sku: string; name: string; unit_price: number };

const PRICE_DEVIATION = 0.1; // 10% from list price

export function validateOrder(
  header: OrderHeaderInput,
  lines: OrderLineInput[],
  catalog: CatalogItem[],
) {
  const issues: string[] = [];
  if (!header.order_number) issues.push("Missing order number");
  if (!header.counterparty) issues.push("Missing customer / supplier");
  if (!header.order_date) issues.push("Missing order date");
  if (header.order_date && header.delivery_date && header.delivery_date < header.order_date) {
    issues.push("Delivery date is before order date");
  }
  if (lines.length === 0) issues.push("No line items found");

  const bySku = new Map(catalog.map((c) => [c.sku.toUpperCase(), c]));
  const lineIssues = lines.map((line) => {
    const li: string[] = [];
    if (!line.sku) li.push("Missing SKU");
    const item = line.sku ? bySku.get(line.sku.toUpperCase()) : undefined;
    if (line.sku && !item) li.push("SKU not in catalogue");
    if (line.quantity <= 0) li.push("Quantity must be positive");
    if (Math.abs(line.quantity * line.unit_price - line.amount) > 0.05) li.push("Amount ≠ qty × price");
    if (item && item.unit_price > 0) {
      const dev = (line.unit_price - item.unit_price) / item.unit_price;
      if (Math.abs(dev) > PRICE_DEVIATION) {
        li.push(`Price ${dev > 0 ? "+" : ""}${(dev * 100).toFixed(0)}% vs list ${item.unit_price.toFixed(2)}`);
      }
    }
    return li;
  });

  const lineTotal = lines.reduce((s, l) => s + l.amount, 0);
  if (header.total != null && Math.abs(lineTotal - header.total) > 0.05) {
    issues.push(`Order total ${header.total.toFixed(2)} ≠ line total ${lineTotal.toFixed(2)}`);
  }

  const lineIssueCount = lineIssues.filter((l) => l.length > 0).length;
  if (lineIssueCount > 0) issues.push(`${lineIssueCount} line(s) need attention`);

  return { issues, lineIssues, status: issues.length ? ("needs_attention" as const) : ("ready" as const) };
}

const csvCell = (v: unknown) => {
  const s = v == null ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function toCsv(rows: Record<string, unknown>[]) {
  if (rows.length === 0) return "";
  const headers = Object.keys(rows[0]);
  return [headers.join(","), ...rows.map((r) => headers.map((h) => csvCell(r[h])).join(","))].join("\r\n");
}
