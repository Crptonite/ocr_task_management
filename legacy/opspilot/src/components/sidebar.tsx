"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  FileCheck2,
  PackageSearch,
  KanbanSquare,
  ClipboardList,
  ScrollText,
  Users,
  LogOut,
  Sparkles,
} from "lucide-react";
import { initials } from "@/lib/format";

const sections = [
  {
    title: "Overview",
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    title: "Workflows",
    items: [
      { href: "/invoices", label: "Invoice checking", icon: FileCheck2 },
      { href: "/orders", label: "Order automation", icon: PackageSearch },
      { href: "/projects", label: "Projects & tasks", icon: KanbanSquare },
    ],
  },
  {
    title: "Records",
    items: [
      { href: "/purchase-orders", label: "Purchase orders", icon: ClipboardList },
      { href: "/audit", label: "Audit log", icon: ScrollText },
      { href: "/team", label: "Team", icon: Users },
    ],
  },
];

export function Sidebar({
  user,
  aiEnabled,
  counts,
  signOut,
}: {
  user: { name: string; role: string };
  aiEnabled: boolean;
  counts: Record<string, number>;
  signOut: () => Promise<void>;
}) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <aside className="flex w-full shrink-0 flex-col border-line bg-surface md:sticky md:top-0 md:h-screen md:w-64 md:border-r">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="grid size-8 place-items-center rounded-lg bg-brand-600 text-white">
          <Sparkles className="size-4" />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">OpsPilot</div>
          <div className="text-xs text-muted">AI back-office workspace</div>
        </div>
      </div>

      <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:gap-5 md:overflow-visible">
        {sections.map((section) => (
          <div key={section.title} className="flex gap-1 md:flex-col">
            <div className="hidden px-2 pb-1 text-[11px] font-medium tracking-wider text-muted uppercase md:block">
              {section.title}
            </div>
            {section.items.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm whitespace-nowrap transition-colors ${
                  isActive(href) ? "bg-brand-50 font-medium text-brand-700" : "text-ink/80 hover:bg-canvas"
                }`}
              >
                <Icon className="size-4 shrink-0" />
                <span className="flex-1">{label}</span>
                {counts[href] ? (
                  <span className="rounded-full bg-amber-100 px-1.5 text-xs font-medium text-amber-800">{counts[href]}</span>
                ) : null}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className="hidden border-t border-line p-4 md:block">
        <div
          className={`mb-3 rounded-lg px-3 py-2 text-xs ${aiEnabled ? "bg-brand-50 text-brand-700" : "bg-amber-50 text-amber-800"}`}
        >
          {aiEnabled ? "AI extraction: OpenAI connected" : "Demo mode: mock AI extraction"}
        </div>
        <div className="flex items-center gap-3">
          <div className="grid size-8 place-items-center rounded-full bg-stone-200 text-xs font-semibold">
            {initials(user.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{user.name}</div>
            <div className="text-xs text-muted capitalize">{user.role}</div>
          </div>
          <form action={signOut}>
            <button className="rounded-md p-1.5 text-muted hover:bg-canvas hover:text-ink" title="Sign out">
              <LogOut className="size-4" />
            </button>
          </form>
        </div>
      </div>
    </aside>
  );
}
