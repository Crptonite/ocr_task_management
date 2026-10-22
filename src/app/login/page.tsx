"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, FileCheck2, PackageSearch, KanbanSquare } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email"));
    const password = String(form.get("password"));
    const supabase = createClient();

    if (mode === "signin") {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) setError(error.message);
      else {
        router.push("/");
        router.refresh();
      }
    } else {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: String(form.get("name") || "") } },
      });
      if (error) setError(error.message);
      else if (data.session) {
        router.push("/");
        router.refresh();
      } else setNotice("Check your inbox to confirm your email, then sign in.");
    }
    setBusy(false);
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <div className="hidden flex-col justify-between bg-brand-700 p-12 text-white md:flex">
        <div className="flex items-center gap-2.5">
          <div className="grid size-9 place-items-center rounded-lg bg-white/15">
            <Sparkles className="size-5" />
          </div>
          <span className="text-lg font-semibold">OpsPilot</span>
        </div>
        <div>
          <h2 className="max-w-md text-3xl leading-tight font-semibold">
            Less data entry. Fewer billing mistakes. Work that actually gets tracked.
          </h2>
          <ul className="mt-8 space-y-4 text-sm text-white/85">
            <li className="flex gap-3">
              <FileCheck2 className="size-5 shrink-0" /> AI reads supplier invoices and flags mismatches against POs.
            </li>
            <li className="flex gap-3">
              <PackageSearch className="size-5 shrink-0" /> Orders extracted, validated and exported for ERP entry.
            </li>
            <li className="flex gap-3">
              <KanbanSquare className="size-5 shrink-0" /> Exceptions become tasks on a shared project board.
            </li>
          </ul>
        </div>
        <p className="text-xs text-white/60">School project prototype · Next.js + Supabase + Claude</p>
      </div>

      <div className="flex items-center justify-center p-6">
        <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
          <div>
            <h1 className="text-2xl font-semibold">{mode === "signin" ? "Welcome back" : "Create your account"}</h1>
            <p className="mt-1 text-sm text-muted">
              {mode === "signin" ? "Sign in to your workspace." : "The first account becomes the workspace admin."}
            </p>
          </div>
          {mode === "signup" && (
            <div>
              <label className="label" htmlFor="name">Full name</label>
              <input id="name" name="name" className="input" required />
            </div>
          )}
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" name="email" type="email" className="input" required autoComplete="email" />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              className="input"
              required
              minLength={6}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
            />
          </div>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          {notice && <p className="rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">{notice}</p>}
          <button className="btn-primary w-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
          <p className="text-center text-sm text-muted">
            {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
            <button
              type="button"
              className="font-medium text-brand-600 hover:underline"
              onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            >
              {mode === "signin" ? "Create an account" : "Sign in"}
            </button>
          </p>
        </form>
      </div>
    </div>
  );
}
