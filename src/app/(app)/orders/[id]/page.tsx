import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, CheckCircle2, RotateCcw, Trash2 } from "lucide-react";
import { ConfirmButton } from "@/components/confirm-button";
import { canReview, requireUser } from "@/lib/supabase/server";
import { signedUrl } from "@/lib/workflow";
import { Badge, StatusBadge } from "@/components/ui";
import { DocumentPreview } from "@/components/document-preview";
import { dateTime } from "@/lib/format";
import { approveOrder, deleteOrder, reopenOrder } from "../actions";
import { OrderEditor } from "./order-editor";

export default async function OrderDetail({ params }: PageProps<"/orders/[id]">) {
  const { id } = await params;
  const { supabase, profile } = await requireUser();

  const { data: order } = await supabase
    .from("orders")
    .select("*, order_lines(*), approver:profiles!orders_approved_by_fkey(full_name)")
    .eq("id", id)
    .maybeSingle();
  if (!order) notFound();

  const url = await signedUrl(supabase, order.file_path);
  const locked = order.status === "approved" || order.status === "exported";
  const lines = ((order.order_lines ?? []) as {
    line_no: number;
    sku: string | null;
    description: string;
    quantity: number;
    unit_price: number;
    amount: number;
    issues: string[];
  }[]).sort((a, b) => a.line_no - b.line_no);
  const approver = order.approver as { full_name: string | null } | null;

  return (
    <>
      <Link href="/orders" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink">
        <ArrowLeft className="size-4" /> Orders
      </Link>

      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight">{order.order_number ?? "Unnumbered order"}</h1>
            <Badge tone={order.order_type === "sales" ? "blue" : "violet"}>
              {order.order_type === "sales" ? "Sales order" : "Purchase order"}
            </Badge>
            <StatusBadge status={order.status} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {order.counterparty ?? "Unknown party"} · {order.file_name}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {locked && (
            <p className="mr-2 text-sm text-muted">
              Approved by {approver?.full_name ?? "a reviewer"} · {dateTime(order.approved_at)}
              {order.exported_at && <> · exported {dateTime(order.exported_at)}</>}
            </p>
          )}
          {order.status === "ready" && canReview(profile) && (
            <form action={approveOrder}>
              <input type="hidden" name="id" value={order.id} />
              <button className="btn-primary">
                <CheckCircle2 className="size-4" /> Approve for ERP export
              </button>
            </form>
          )}
          {order.status === "approved" && canReview(profile) && (
            <form action={reopenOrder}>
              <input type="hidden" name="id" value={order.id} />
              <button className="btn-secondary">
                <RotateCcw className="size-4" /> Reopen
              </button>
            </form>
          )}
          {canReview(profile) && (
            <form action={deleteOrder}>
              <input type="hidden" name="id" value={order.id} />
              <ConfirmButton
                message="Delete this order, its file and its exception task? This cannot be undone."
                className="btn-secondary text-red-700"
              >
                <Trash2 className="size-4" /> Delete
              </ConfirmButton>
            </form>
          )}
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-5">
        <div className="xl:col-span-2">
          <DocumentPreview url={url} fileName={order.file_name} />
        </div>
        <div className="xl:col-span-3">
          <OrderEditor
            id={order.id}
            locked={locked}
            initialIssues={order.issues ?? []}
            initialHeader={{
              order_type: order.order_type,
              order_number: order.order_number,
              counterparty: order.counterparty,
              order_date: order.order_date,
              delivery_date: order.delivery_date,
              currency: order.currency,
              total: order.total == null ? null : Number(order.total),
            }}
            initialLines={lines.map((l) => ({
              sku: l.sku,
              description: l.description,
              quantity: Number(l.quantity),
              unit_price: Number(l.unit_price),
              amount: Number(l.amount),
              issues: l.issues ?? [],
            }))}
          />
        </div>
      </div>
    </>
  );
}
