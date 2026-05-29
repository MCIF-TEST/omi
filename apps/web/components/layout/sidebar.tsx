"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Search, Network, FileSearch, Bell,
  Eye, Settings, Layers, Boxes,
} from "lucide-react";

import { Logo } from "@/components/shared/logo";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: typeof LayoutDashboard };

const NAV_GROUPS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/investigate", label: "Investigate", icon: Search },
    ],
  },
  {
    heading: "Intelligence",
    items: [
      { href: "/content", label: "Content", icon: Layers },
      { href: "/narratives", label: "Narratives", icon: Eye },
      { href: "/graph", label: "Graph", icon: Network },
    ],
  },
  {
    heading: "Operations",
    items: [
      { href: "/monitoring", label: "Monitoring", icon: Bell },
      { href: "/investigations", label: "Investigations", icon: FileSearch },
      { href: "/bulk", label: "Bulk", icon: Boxes },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-card/30 backdrop-blur-xl md:flex">
      <div className="flex h-16 items-center border-b border-border px-6">
        <Logo />
      </div>

      <nav className="flex flex-1 flex-col gap-6 overflow-y-auto p-3 pt-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.heading} className="flex flex-col gap-1">
            <div className="px-3 pb-1 text-2xs font-semibold uppercase tracking-widest text-muted-foreground/60">
              {group.heading}
            </div>
            {group.items.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all",
                    active
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-brand-gradient" />
                  )}
                  <item.icon
                    size={18}
                    className={cn(
                      "transition-transform",
                      !active && "group-hover:scale-110",
                    )}
                  />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-3">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
            pathname.startsWith("/settings")
              ? "bg-primary/10 text-primary"
              : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          )}
        >
          <Settings size={18} />
          Settings
        </Link>
      </div>
    </aside>
  );
}
