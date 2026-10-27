import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options),
            );
          } catch {
            // Called from a Server Component; the proxy refreshes the session instead.
          }
        },
      },
    },
  );
}

export type Profile = {
  id: string;
  full_name: string | null;
  email: string | null;
  role: "admin" | "reviewer" | "staff";
};

/** Returns the client plus the signed-in user's profile, or redirects to /login. */
export async function requireUser() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const loadProfile = () =>
    supabase.from("profiles").select("id, full_name, email, role").eq("id", user.id).maybeSingle<Profile>();

  let { data: profile } = await loadProfile();
  if (!profile) {
    // Account created before the schema existed: create its profile so
    // foreign keys like invoices.uploaded_by are satisfied.
    const { error } = await supabase.rpc("ensure_profile");
    if (error) throw new Error(`Your user profile is missing and could not be created: ${error.message}`);
    ({ data: profile } = await loadProfile());
    if (!profile) throw new Error("Your user profile is missing. Run the latest Supabase migration.");
  }

  return { supabase, user, profile };
}

export function canReview(profile: Profile) {
  return profile.role === "admin" || profile.role === "reviewer";
}
