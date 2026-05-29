import Link from "next/link";
import {
  ArrowRight, Network, Brain, Eye, Activity, Fingerprint,
  ShieldCheck, GitBranch, Sparkles,
} from "lucide-react";

import { Logo } from "@/components/shared/logo";

const FEATURES = [
  {
    icon: Fingerprint,
    title: "Behavioral fingerprinting",
    body: "A 19-dimensional fingerprint of posting cadence, timing entropy, and linguistic patterns — unique per account, comparable across millions.",
    tint: "primary",
  },
  {
    icon: Network,
    title: "Coordination detection",
    body: "Surface clusters of accounts acting in concert across reply threads, shared timing, and matching behavioral DNA.",
    tint: "secondary",
  },
  {
    icon: Brain,
    title: "OmiScore intelligence",
    body: "Every account distilled to one explainable score — authenticity, coordination, amplification, spam, and AI generation, each traceable to evidence.",
    tint: "accent",
  },
  {
    icon: Eye,
    title: "Narrative tracking",
    body: "Follow how talking points propagate and mutate across comment sections, in real time.",
    tint: "primary",
  },
  {
    icon: Activity,
    title: "Continuous monitoring",
    body: "Watchlist any account or channel and get alerted the moment its risk profile shifts.",
    tint: "secondary",
  },
  {
    icon: GitBranch,
    title: "Self-improving engine",
    body: "Every scan sharpens the model. The more OmiSphere sees, the better it gets — by design.",
    tint: "accent",
  },
];

const STATS = [
  { value: "19-D", label: "behavioral fingerprint" },
  { value: "8", label: "independent detectors" },
  { value: "6", label: "coordination signals" },
  { value: "0–100", label: "explainable OmiScore" },
];

const tintClass: Record<string, string> = {
  primary: "text-primary",
  secondary: "text-secondary",
  accent: "text-accent",
};

export default function LandingPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Ambient background: faint grid + drifting auroras */}
      <div className="pointer-events-none absolute inset-0 bg-grid-faint bg-[size:64px_64px] opacity-[0.15]" />
      <div className="pointer-events-none absolute left-1/2 top-[-12rem] h-[42rem] w-[60rem] -translate-x-1/2 rounded-full bg-primary/20 blur-[140px] animate-aurora" />
      <div className="pointer-events-none absolute right-[-10rem] top-[10rem] h-[34rem] w-[40rem] rounded-full bg-secondary/15 blur-[130px] animate-aurora [animation-delay:3s]" />

      <div className="relative z-10">
        {/* Nav */}
        <nav className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Logo />
          <div className="flex items-center gap-1 text-sm sm:gap-6">
            <Link href="/about" className="hidden rounded-lg px-3 py-2 text-muted-foreground transition-colors hover:text-foreground sm:block">
              About
            </Link>
            <Link href="/pricing" className="hidden rounded-lg px-3 py-2 text-muted-foreground transition-colors hover:text-foreground sm:block">
              Pricing
            </Link>
            <Link href="/login" className="rounded-lg px-3 py-2 text-muted-foreground transition-colors hover:text-foreground">
              Login
            </Link>
            <Link
              href="/signup"
              className="group inline-flex items-center gap-1.5 rounded-lg bg-brand-gradient px-4 py-2 font-medium text-primary-foreground glow-primary"
            >
              Get Started
              <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
          </div>
        </nav>

        {/* Hero */}
        <main className="mx-auto max-w-7xl px-6">
          <section className="flex flex-col items-center py-20 text-center md:py-32">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-card/50 px-4 py-1.5 text-xs text-muted-foreground backdrop-blur animate-fade-in">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
              </span>
              Authenticity Intelligence Engine — now in early access
            </div>

            <h1 className="max-w-4xl text-balance text-5xl font-bold leading-[1.04] tracking-tight animate-fade-in-up md:text-7xl">
              See who&apos;s <span className="text-gradient">real</span>.
              <br />
              Detect who&apos;s <span className="bg-gradient-to-r from-secondary to-destructive bg-clip-text text-transparent">not</span>.
            </h1>

            <p className="mt-6 max-w-2xl text-pretty text-lg text-muted-foreground animate-fade-in-up [animation-delay:80ms] md:text-xl">
              OmiSphere analyzes behavioral fingerprints, posting patterns, and
              network coordination to surface bots, sock puppets, and
              AI-generated content — with calibrated probabilities, not guesses.
            </p>

            <div className="mt-10 flex flex-col items-center gap-4 animate-fade-in-up [animation-delay:160ms] sm:flex-row">
              <Link
                href="/signup"
                className="group inline-flex items-center gap-2 rounded-lg bg-brand-gradient px-6 py-3 font-medium text-primary-foreground glow-primary"
              >
                Start investigating
                <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
              </Link>
              <Link
                href="/about"
                className="rounded-lg border border-white/10 bg-card/40 px-6 py-3 font-medium backdrop-blur transition-colors hover:border-primary/40 hover:bg-card"
              >
                How it works
              </Link>
            </div>

            {/* Stat strip */}
            <div className="mt-20 grid w-full max-w-3xl grid-cols-2 gap-px overflow-hidden rounded-2xl glass animate-fade-in-up [animation-delay:240ms] sm:grid-cols-4">
              {STATS.map((s) => (
                <div key={s.label} className="bg-card/20 px-4 py-6 text-center">
                  <div className="font-mono text-2xl font-bold text-gradient sm:text-3xl">{s.value}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{s.label}</div>
                </div>
              ))}
            </div>
          </section>
        </main>

        {/* Feature grid */}
        <section className="mx-auto max-w-7xl px-6 py-20">
          <div className="mx-auto mb-14 max-w-2xl text-center">
            <div className="mb-3 inline-flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-primary">
              <Sparkles size={13} /> The engine
            </div>
            <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
              Intelligence, not guesswork
            </h2>
            <p className="mt-3 text-muted-foreground">
              Six layers of analysis converge into one explainable verdict — every
              signal traceable to the evidence behind it.
            </p>
          </div>

          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="ring-gradient group relative overflow-hidden rounded-2xl bg-card/40 p-6 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:bg-card/70"
              >
                <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-background/60">
                  <f.icon className={tintClass[f.tint]} size={20} />
                </div>
                <h3 className="mb-2 font-semibold">{f.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-5xl px-6 py-20">
          <div className="ring-gradient relative overflow-hidden rounded-3xl bg-gradient-to-br from-card to-card/20 p-12 text-center">
            <div className="pointer-events-none absolute inset-0 bg-brand-radial opacity-60" />
            <div className="pointer-events-none absolute left-1/2 top-0 h-40 w-[36rem] -translate-x-1/2 rounded-full bg-primary/20 blur-[100px]" />
            <div className="relative z-10">
              <ShieldCheck className="mx-auto mb-5 text-primary" size={36} />
              <h2 className="text-3xl font-bold md:text-4xl">Ready to see clearly?</h2>
              <p className="mx-auto mt-4 max-w-xl text-muted-foreground">
                Join analysts, researchers, and platform teams using OmiSphere to
                cut through the noise.
              </p>
              <Link
                href="/signup"
                className="group mt-8 inline-flex items-center gap-2 rounded-lg bg-brand-gradient px-7 py-3 font-medium text-primary-foreground glow-primary"
              >
                Get started free
                <ArrowRight size={18} className="transition-transform group-hover:translate-x-1" />
              </Link>
            </div>
          </div>
        </section>

        {/* Footer */}
        <footer className="mx-auto max-w-7xl border-t border-border px-6 py-10">
          <div className="flex flex-col items-center justify-between gap-4 text-sm text-muted-foreground md:flex-row">
            <Logo />
            <p>© 2026 OmiSphere. Authenticity intelligence.</p>
          </div>
        </footer>
      </div>
    </div>
  );
}
