import { redirect } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { requireUser, createClient } from "@/lib/supabase/server";
import { aiEnabled } from "@/lib/ai";

async function signOut() {
  "use server";
  const supabase = await createClient();
  await supabase.auth.signOut();
  redirect("/login");
}

export default async function AppLayout({ children }: LayoutProps<"/">) {
  const { supabase, profile } = await requireUser();

  const [flagged, attention] = await Promise.all([
    supabase.from("invoices").select("id", { count: "exact", head: true }).eq("status", "flagged"),
    supabase.from("orders").select("id", { count: "exact", head: true }).eq("status", "needs_attention"),
  ]);

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <Sidebar
        user={{ name: profile.full_name ?? profile.email ?? "User", role: profile.role }}
        aiEnabled={aiEnabled}
        counts={{ "/invoices": flagged.count ?? 0, "/orders": attention.count ?? 0 }}
        signOut={signOut}
      />
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
