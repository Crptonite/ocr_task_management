import "server-only";
import OpenAI from "openai";
import { zodTextFormat } from "openai/helpers/zod";
import type { ResponseInputContent } from "openai/resources/responses/responses";
import { z } from "zod";

const MODEL = process.env.OPENAI_MODEL || "gpt-5.4-mini";

/** Without an API key the app runs in demo mode with realistic mock output. */
export const aiEnabled = Boolean(process.env.OPENAI_API_KEY);

const client = aiEnabled ? new OpenAI() : null;

const LineSchema = z.object({
  sku: z.string().nullable(),
  description: z.string(),
  quantity: z.number(),
  unit_price: z.number(),
  amount: z.number(),
});

export const InvoiceSchema = z.object({
  invoice_number: z.string().nullable(),
  supplier_name: z.string().nullable(),
  po_number: z.string().nullable().describe("Purchase order number referenced on the invoice"),
  invoice_date: z.string().nullable().describe("YYYY-MM-DD"),
  due_date: z.string().nullable().describe("YYYY-MM-DD"),
  currency: z.string().nullable().describe("ISO 4217 code"),
  subtotal: z.number().nullable(),
  tax: z.number().nullable(),
  total: z.number().nullable(),
  lines: z.array(LineSchema),
  confidence: z.number().describe("0 to 1: how legible and complete the document was"),
});
export type InvoiceExtraction = z.infer<typeof InvoiceSchema>;

export const OrderSchema = z.object({
  order_type: z.enum(["purchase", "sales"]),
  order_number: z.string().nullable(),
  counterparty: z.string().nullable().describe("Customer (sales order) or supplier (purchase order)"),
  order_date: z.string().nullable().describe("YYYY-MM-DD"),
  delivery_date: z.string().nullable().describe("YYYY-MM-DD"),
  currency: z.string().nullable(),
  total: z.number().nullable(),
  lines: z.array(LineSchema),
});
export type OrderExtraction = z.infer<typeof OrderSchema>;

const TaskSuggestionSchema = z.object({
  tasks: z.array(
    z.object({
      title: z.string(),
      description: z.string(),
      priority: z.enum(["low", "medium", "high"]),
      due_in_days: z.number().describe("Suggested days from today until due"),
    }),
  ),
});
export type TaskSuggestion = z.infer<typeof TaskSuggestionSchema>["tasks"][number];

type DocInput = { data: Buffer; mediaType: string };

function documentBlock({ data, mediaType }: DocInput): ResponseInputContent {
  const dataUrl = `data:${mediaType};base64,${data.toString("base64")}`;
  if (mediaType === "application/pdf") {
    return { type: "input_file", filename: "document.pdf", file_data: dataUrl };
  }
  return { type: "input_image", image_url: dataUrl, detail: "high" };
}

async function parse<T extends z.ZodType>(
  schema: T,
  system: string,
  content: ResponseInputContent[],
): Promise<z.infer<T>> {
  const response = await client!.responses.parse({
    model: MODEL,
    instructions: system,
    input: [{ role: "user", content }],
    text: { format: zodTextFormat(schema, "result") },
  });
  if (!response.output_parsed) throw new Error("The AI model returned an unreadable result.");
  return response.output_parsed as z.infer<T>;
}

/** `demoPo` is only used in demo mode to build a plausible invoice from real PO data. */
export async function extractInvoice(doc: DocInput, demoPo?: DemoPo | null): Promise<InvoiceExtraction> {
  if (!client) return mockInvoice(demoPo ?? null);
  return parse(
    InvoiceSchema,
    "You extract data from supplier invoices for an accounts-payable team. Copy values exactly as printed; " +
      "use null for anything not on the document. Never invent line items.",
    [documentBlock(doc), { type: "input_text", text: "Extract this supplier invoice." }],
  );
}

export async function extractOrder(doc: DocInput): Promise<OrderExtraction> {
  if (!client) return mockOrder();
  return parse(
    OrderSchema,
    "You extract purchase and sales orders for ERP data entry. Copy values exactly as printed; " +
      "use null for anything not on the document. Never invent line items.",
    [documentBlock(doc), { type: "input_text", text: "Extract this order document." }],
  );
}

export async function suggestTasks(brief: string, projectName: string): Promise<TaskSuggestion[]> {
  if (!client) return mockTasks(projectName);
  const result = await parse(
    TaskSuggestionSchema,
    "You are a project coordinator at a furniture manufacturer. Break project briefs into 4-8 concrete, " +
      "assignable tasks with short imperative titles.",
    [{ type: "input_text", text: `Project: ${projectName}\n\nBrief:\n${brief}` }],
  );
  return result.tasks;
}

// ---------------------------------------------------------------------------
// Demo-mode mocks. The invoice mock is fed real PO data by the caller so the
// comparison engine has something meaningful to flag.
// ---------------------------------------------------------------------------
export type DemoPo = {
  po_number: string;
  supplier: string;
  lines: { sku: string | null; description: string; quantity: number; unit_price: number }[];
};

function mockInvoice(po: DemoPo | null): InvoiceExtraction {
  if (!po) {
    return {
      invoice_number: `INV-${Math.floor(Math.random() * 90000 + 10000)}`,
      supplier_name: "Unknown Supplier",
      po_number: null,
      invoice_date: new Date().toISOString().slice(0, 10),
      due_date: null,
      currency: "SGD",
      subtotal: 100,
      tax: 9,
      total: 109,
      lines: [{ sku: null, description: "Misc goods", quantity: 1, unit_price: 100, amount: 100 }],
      confidence: 0.62,
    };
  }
  // Randomly pick a scenario: clean match, price creep, or over-billed quantity.
  const scenario = Math.floor(Math.random() * 3);
  const lines = po.lines.map((l, i) => {
    let unit_price = l.unit_price;
    let quantity = l.quantity;
    if (scenario === 1 && i === 0) unit_price = Math.round(l.unit_price * 1.08 * 100) / 100;
    if (scenario === 2 && i === po.lines.length - 1) quantity = l.quantity + 10;
    return { sku: l.sku, description: l.description, quantity, unit_price, amount: Math.round(quantity * unit_price * 100) / 100 };
  });
  const subtotal = Math.round(lines.reduce((s, l) => s + l.amount, 0) * 100) / 100;
  const tax = Math.round(subtotal * 0.09 * 100) / 100;
  const today = new Date();
  const due = new Date(today.getTime() + 30 * 86400000);
  return {
    invoice_number: `INV-${today.getFullYear()}-${Math.floor(Math.random() * 9000 + 1000)}`,
    supplier_name: po.supplier,
    po_number: po.po_number,
    invoice_date: today.toISOString().slice(0, 10),
    due_date: due.toISOString().slice(0, 10),
    currency: "SGD",
    subtotal,
    tax,
    total: Math.round((subtotal + tax) * 100) / 100,
    lines,
    confidence: 0.94,
  };
}

function mockOrder(): OrderExtraction {
  const lines = [
    { sku: "SOFA-AURA-3S", description: "Aura 3-seater sofa, bouclé ivory", quantity: 4, unit_price: 1890, amount: 7560 },
    { sku: "TBL-OAK-180", description: "Oslo oak dining table 180cm", quantity: 6, unit_price: 1250, amount: 7500 },
    { sku: "CHR-OAK-DIN", description: "Oslo oak dining chair", quantity: 36, unit_price: 210, amount: 7560 },
    { sku: "LMP-BRS-FL", description: "Brass floor lamp", quantity: 4, unit_price: 380, amount: 1520 },
  ];
  return {
    order_type: "sales",
    order_number: `SO-${Math.floor(Math.random() * 90000 + 10000)}`,
    counterparty: "The Loft Hotel Group",
    order_date: new Date().toISOString().slice(0, 10),
    delivery_date: new Date(Date.now() + 21 * 86400000).toISOString().slice(0, 10),
    currency: "SGD",
    total: 24140,
    lines,
  };
}

function mockTasks(projectName: string): TaskSuggestion[] {
  return [
    { title: `Confirm scope and budget for ${projectName}`, description: "Agree deliverables, budget ceiling and sign-off owner.", priority: "high", due_in_days: 3 },
    { title: "Collect supplier quotations", description: "Request at least three quotes for major materials.", priority: "medium", due_in_days: 7 },
    { title: "Draft production schedule", description: "Map workshop capacity against the delivery date.", priority: "medium", due_in_days: 10 },
    { title: "Book delivery and installation", description: "Reserve logistics slot and on-site installation crew.", priority: "low", due_in_days: 14 },
    { title: "Final quality inspection", description: "Inspect finished pieces against spec before dispatch.", priority: "high", due_in_days: 20 },
  ];
}
