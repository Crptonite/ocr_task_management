// Renders a supplier invoice as a PDF (runs in the browser or on the server).
import { PDFDocument, StandardFonts, rgb, type PDFFont, type PDFPage } from "pdf-lib";

export type InvoiceDoc = {
  supplier: { name: string; address: string; email: string; reg_no: string };
  bill_to: { name: string; address: string };
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  po_number: string;
  currency: string;
  tax_rate: number; // percent, e.g. 9
  lines: { sku: string; description: string; quantity: number; unit_price: number }[];
  notes: string;
};

export function invoiceTotals(doc: Pick<InvoiceDoc, "lines" | "tax_rate">) {
  const round = (n: number) => Math.round(n * 100) / 100;
  const subtotal = round(doc.lines.reduce((s, l) => s + round(l.quantity * l.unit_price), 0));
  const tax = round((subtotal * doc.tax_rate) / 100);
  return { subtotal, tax, total: round(subtotal + tax) };
}

// Standard PDF fonts only cover WinAnsi; swap anything else for a safe character.
function safe(text: string) {
  return text
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/[^\x20-\x7E\xA0-\xFF€•…]/g, "?");
}

const A4 = { w: 595.28, h: 841.89 };
const M = 48; // page margin
const INK = rgb(0.11, 0.106, 0.094);
const MUTED = rgb(0.435, 0.42, 0.384);
const LINE = rgb(0.906, 0.894, 0.867);
const BRAND = rgb(0.145, 0.4, 0.263);
const ZEBRA = rgb(0.965, 0.961, 0.949);

export async function buildInvoicePdf(doc: InvoiceDoc): Promise<Uint8Array> {
  const pdf = await PDFDocument.create();
  pdf.setTitle(`Invoice ${doc.invoice_number}`);
  pdf.setAuthor(doc.supplier.name);
  pdf.setCreator("OpsPilot invoice generator");

  const regular = await pdf.embedFont(StandardFonts.Helvetica);
  const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
  const num = (n: number) => n.toLocaleString("en-SG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const money = (n: number) => `${doc.currency} ${num(n)}`;

  const text = (page: PDFPage, s: string, x: number, y: number, size = 9, font: PDFFont = regular, color = INK) =>
    page.drawText(safe(s), { x, y, size, font, color });
  const right = (page: PDFPage, s: string, xRight: number, y: number, size = 9, font: PDFFont = regular, color = INK) =>
    text(page, s, xRight - font.widthOfTextAtSize(safe(s), size), y, size, font, color);
  const fit = (s: string, width: number, size = 9, font: PDFFont = regular) => {
    let out = safe(s);
    if (font.widthOfTextAtSize(out, size) <= width) return out;
    while (out.length > 1 && font.widthOfTextAtSize(out + "...", size) > width) out = out.slice(0, -1);
    return out + "...";
  };

  // Columns: #, SKU, Description, Qty, Unit price, Amount (right edges for numbers).
  const col = { no: M, sku: M + 22, desc: M + 112, qtyR: A4.w - M - 170, priceR: A4.w - M - 85, amtR: A4.w - M };

  let page = pdf.addPage([A4.w, A4.h]);
  let y = A4.h - M;

  // --- Header -------------------------------------------------------------
  page.drawRectangle({ x: 0, y: A4.h - 6, width: A4.w, height: 6, color: BRAND });
  text(page, doc.supplier.name || "Supplier", M, y - 10, 16, bold);
  let sy = y - 28;
  for (const line of [...doc.supplier.address.split("\n"), doc.supplier.email, doc.supplier.reg_no && `Reg. No. ${doc.supplier.reg_no}`]) {
    if (!line) continue;
    text(page, line, M, sy, 9, regular, MUTED);
    sy -= 12;
  }

  right(page, "TAX INVOICE", A4.w - M, y - 12, 20, bold, BRAND);
  const meta: [string, string][] = [
    ["Invoice No.", doc.invoice_number],
    ["Invoice date", doc.invoice_date],
    ["Due date", doc.due_date],
    ["PO number", doc.po_number || "-"],
  ];
  let my = y - 34;
  for (const [k, v] of meta) {
    right(page, k, A4.w - M - 110, my, 9, regular, MUTED);
    right(page, v, A4.w - M, my, 9, bold);
    my -= 13;
  }

  y = Math.min(sy, my) - 18;
  text(page, "BILL TO", M, y, 8, bold, MUTED);
  y -= 14;
  text(page, doc.bill_to.name, M, y, 10, bold);
  y -= 13;
  for (const line of doc.bill_to.address.split("\n").filter(Boolean)) {
    text(page, line, M, y, 9, regular, MUTED);
    y -= 12;
  }
  y -= 16;

  // --- Line items -----------------------------------------------------------
  const tableHeader = () => {
    page.drawRectangle({ x: M, y: y - 6, width: A4.w - 2 * M, height: 20, color: BRAND });
    const white = rgb(1, 1, 1);
    text(page, "#", col.no + 4, y, 8, bold, white);
    text(page, "SKU", col.sku, y, 8, bold, white);
    text(page, "DESCRIPTION", col.desc, y, 8, bold, white);
    right(page, "QTY", col.qtyR, y, 8, bold, white);
    right(page, "UNIT PRICE", col.priceR, y, 8, bold, white);
    right(page, "AMOUNT", col.amtR - 4, y, 8, bold, white);
    y -= 22;
  };
  tableHeader();

  doc.lines.forEach((l, i) => {
    if (y < 150) {
      page = pdf.addPage([A4.w, A4.h]);
      y = A4.h - M;
      tableHeader();
    }
    if (i % 2 === 1) page.drawRectangle({ x: M, y: y - 6, width: A4.w - 2 * M, height: 20, color: ZEBRA });
    text(page, String(i + 1), col.no + 4, y, 9, regular, MUTED);
    text(page, fit(l.sku || "-", col.desc - col.sku - 8, 8), col.sku, y, 8);
    text(page, fit(l.description, col.qtyR - col.desc - 50), col.desc, y);
    right(page, String(l.quantity), col.qtyR, y);
    right(page, num(l.unit_price), col.priceR, y);
    right(page, num(Math.round(l.quantity * l.unit_price * 100) / 100), col.amtR - 4, y);
    y -= 20;
  });
  page.drawLine({ start: { x: M, y: y + 8 }, end: { x: A4.w - M, y: y + 8 }, thickness: 0.8, color: LINE });

  // --- Totals ---------------------------------------------------------------
  if (y < 140) {
    page = pdf.addPage([A4.w, A4.h]);
    y = A4.h - M;
  }
  const { subtotal, tax, total } = invoiceTotals(doc);
  y -= 10;
  const labelR = A4.w - M - 120;
  right(page, "Subtotal", labelR, y, 9, regular, MUTED);
  right(page, money(subtotal), A4.w - M - 4, y);
  y -= 15;
  right(page, `GST ${doc.tax_rate}%`, labelR, y, 9, regular, MUTED);
  right(page, money(tax), A4.w - M - 4, y);
  y -= 10;
  page.drawRectangle({ x: labelR - 70, y: y - 18, width: A4.w - M - (labelR - 70), height: 24, color: ZEBRA });
  right(page, "Total due", labelR, y - 10, 10, bold);
  right(page, money(total), A4.w - M - 4, y - 10, 11, bold, BRAND);
  y -= 44;

  // --- Notes / footer -------------------------------------------------------
  if (doc.notes.trim()) {
    text(page, "NOTES", M, y, 8, bold, MUTED);
    y -= 13;
    for (const line of doc.notes.split("\n")) {
      text(page, fit(line, A4.w - 2 * M), M, y, 9, regular, MUTED);
      y -= 12;
    }
  }
  const pages = pdf.getPages();
  pages.forEach((p, i) => {
    p.drawLine({ start: { x: M, y: 40 }, end: { x: A4.w - M, y: 40 }, thickness: 0.5, color: LINE });
    text(p, `${doc.supplier.name} · Invoice ${doc.invoice_number}`, M, 28, 7.5, regular, MUTED);
    right(p, `Page ${i + 1} of ${pages.length}`, A4.w - M, 28, 7.5, regular, MUTED);
  });

  return pdf.save();
}
