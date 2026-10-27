import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { toCsv } from "@/lib/orders";
import { audit } from "@/lib/workflow";

// Exports every approved (not yet exported) order as an ERP-ready CSV and marks them exported.
export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { data: orders } = await supabase
    .from("orders")
    .select("id, order_type, order_number, counterparty, order_date, delivery_date, currency, order_lines(line_no, sku, description, quantity, unit_price, amount)")
    .eq("status", "approved")
    .order("order_date");

  const rows = (orders ?? []).flatMap((o) =>
    (o.order_lines ?? [])
      .sort((a, b) => a.line_no - b.line_no)
      .map((l) => ({
        DocumentType: o.order_type === "sales" ? "SO" : "PO",
        OrderNo: o.order_number,
        Party: o.counterparty,
        OrderDate: o.order_date,
        DeliveryDate: o.delivery_date,
        Currency: o.currency,
        LineNo: l.line_no,
        ItemNo: l.sku,
        Description: l.description,
        Quantity: l.quantity,
        UnitPrice: l.unit_price,
        LineAmount: l.amount,
      })),
  );

  if (!orders?.length) {
    return NextResponse.json({ error: "No approved orders to export" }, { status: 404 });
  }

  const ids = orders.map((o) => o.id);
  await supabase.from("orders").update({ status: "exported", exported_at: new Date().toISOString() }).in("id", ids);
  await Promise.all(ids.map((id) => audit(supabase, user.id, "order", id, "exported")));

  const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
  return new NextResponse(toCsv(rows), {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="erp-orders-${stamp}.csv"`,
    },
  });
}
