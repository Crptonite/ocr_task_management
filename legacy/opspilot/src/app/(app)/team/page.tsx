import { revalidatePath } from "next/cache";
import { requireUser } from "@/lib/supabase/server";
import { PageHeader } from "@/components/ui";
import { initials } from "@/lib/format";
import { audit } from "@/lib/workflow";

async function setRole(formData: FormData) {
  "use server";
  const { supabase, profile } = await requireUser();
  if (profile.role !== "admin") throw new Error("Only admins can change roles.");
  const id = String(formData.get("id"));
  const role = String(formData.get("role"));
  if (!["admin", "reviewer", "staff"].includes(role)) throw new Error("Invalid role");
  await supabase.from("profiles").update({ role }).eq("id", id);
  await audit(supabase, profile.id, "profile", id, `role → ${role}`);
  revalidatePath("/team");
}

const roleHelp = {
  admin: "Everything, including managing roles",
  reviewer: "Approve/reject invoices and approve orders",
  staff: "Upload documents, fix orders, manage tasks",
};

export default async function TeamPage() {
  const { supabase, profile } = await requireUser();
  const { data: members } = await supabase.from("profiles").select("id, full_name, email, role, created_at").order("created_at");

  return (
    <>
      <PageHeader title="Team" description="Who can do what. New sign-ups join as staff." />
      <div className="mb-6 grid gap-3 sm:grid-cols-3">
        {Object.entries(roleHelp).map(([role, help]) => (
          <div key={role} className="card p-4">
            <div className="text-sm font-medium capitalize">{role}</div>
            <div className="text-xs text-muted">{help}</div>
          </div>
        ))}
      </div>
      <div className="card divide-y divide-line">
        {(members ?? []).map((m) => (
          <div key={m.id} className="flex flex-wrap items-center gap-4 px-5 py-3">
            <div className="grid size-9 place-items-center rounded-full bg-stone-200 text-xs font-semibold">
              {initials(m.full_name ?? m.email)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium">
                {m.full_name} {m.id === profile.id && <span className="text-xs text-muted">(you)</span>}
              </div>
              <div className="text-xs text-muted">{m.email}</div>
            </div>
            {profile.role === "admin" && m.id !== profile.id ? (
              <form action={setRole} className="flex items-center gap-2">
                <input type="hidden" name="id" value={m.id} />
                <select name="role" defaultValue={m.role} className="input w-32 py-1.5">
                  <option value="staff">Staff</option>
                  <option value="reviewer">Reviewer</option>
                  <option value="admin">Admin</option>
                </select>
                <button className="btn-secondary py-1.5">Save</button>
              </form>
            ) : (
              <span className="text-sm text-muted capitalize">{m.role}</span>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
