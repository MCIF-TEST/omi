import Link from "next/link";
import {
  Search, Network, Eye, Bell, ArrowRight, Activity,
  ShieldAlert, Layers, Sparkles,
} from "lucide-react";

import { getServerUser } from "@/lib/auth";
import { apiFetch } from "@/lib/api";

type DashboardStats = {
  total_scans: number;
  high_risk_count: number;
  narratives_tracked: number;
  active_watchlists: number;
};

async function getStats(): Promise<DashboardStats | null> {
  try {
    return await apiFetch<DashboardStats>("/v1/metrics/dashboard");
  } catch {
    return null;
  }
}

const TINTS = {
  primary: {
    icon: "text-primary",
    chip: "bg-primary/10 border-primary/20",
    glow: "group-hover:shadow-glow",
  },
  destructive: {
    icon: "text-destructive",
    chip: "bg-destructive/10 border-destructive/20",
    glow: "group-hover:shadow-[0_0_40px_-8px_hsl(var(--destructive)/0.45)]",
  },
  secondary: {
    icon: "text-secondary",
    chip: "bg-secondary/10 border-secondary/20",
    glow: "group-hover:shadow-glow-secondary",
  },
  accent: {
    icon: "text-accent",
    chip: "bg-accent/10 border-accent/20",
    glow: "group-hover:shadow-glow-accent",
  },
} as const;

export default async function DashboardPage() {
  const [user, stats] = await Promise.all([getServerUser(), getStats()]);

  const cards = [
    { label: "Total scans", value: stats?.total_scans ?? "—", icon: Activity, href: "/investigations", tint: "primary" as const },
    { label: "High-risk findings", value: stats?.high_risk_count ?? "—", icon: ShieldAlert, href: "/investigations", tint: "destructive" as const },
    { label: "Narratives tracked", value: stats?.narratives_tracked ?? "—", icon: Eye, href: "/narratives", tint: "secondary" as const },
    { label: "Active watchlists", value: stats?.active_watchlists ?? "—", icon: Bell, href: "/monitoring", tint: "accent" as const },
  ];

  const actions = [
    { href: "/investigate", icon: Search, title: "New investigation", body: "Scan an account, video, or comment section." },
    { href: "/content", icon: Layers, title: "Browse content", body: "Review tracked videos and threads." },
    { href: "/graph", icon: Network, title: "Explore graph", body: "Visualize coordination networks." },
  ];

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      {/* Header */}
      <div className="mb-8 animate-fade-in">
        <div className="mb-1.5 inline-flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-primary">
          <Sparkles size={13} /> Authenticity Intelligence
        </div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back{user ? `, ${user.email.split("@")[0]}` : ""}
        </h1>
        <p className="mt-1 text-muted-foreground">
          Here&apos;s what&apos;s happening across your authenticity intelligence.
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c, i) => {
          const t = TINTS[c.tint];
          return (
            <Link
              key={c.label}
              href={c.href}
              style={{ animationDelay: `${i * 60}ms` }}
              className={`group animate-fade-in-up rounded-2xl glass p-5 transition-all duration-300 hover:-translate-y-1 ${t.glow}`}
            >
              <div className="flex items-center justify-between">
                <div className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border ${t.chip}`}>
                  <c.icon className={t.icon} size={19} />
                </div>
                <ArrowRight size={16} className="text-muted-foreground opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
              </div>
              <div className="mt-4 font-mono text-3xl font-bold tabular-nums">{c.value}</div>
              <div className="mt-1 text-sm text-muted-foreground">{c.label}</div>
            </Link>
          );
        })}
      </div>

      {/* Quick actions */}
      <div className="mt-10">
        <h2 className="mb-4 text-lg font-semibold">Quick actions</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {actions.map((a, i) => (
            <Link
              key={a.href}
              href={a.href}
              style={{ animationDelay: `${(i + 4) * 60}ms` }}
              className="ring-gradient group relative animate-fade-in-up overflow-hidden rounded-2xl bg-card/40 p-5 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:bg-card/70"
            >
              <div className="mb-3 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-background/60">
                <a.icon className="text-primary" size={21} />
              </div>
              <h3 className="flex items-center gap-1.5 font-semibold">
                {a.title}
                <ArrowRight size={15} className="text-muted-foreground opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100" />
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">{a.body}</p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
