import Link from "next/link";
import {
  ArrowLeft, Fingerprint, Network, Brain, Eye, Activity, GitBranch,
} from "lucide-react";

import { Logo } from "@/components/shared/logo";

const LAYERS = [
  {
    icon: Fingerprint,
    title: "Behavioral fingerprinting",
    body: "Every account is reduced to a 19-dimensional behavioral fingerprint — posting cadence, timing entropy, linguistic patterns, profile shape. Platform-agnostic, so the same model transfers across networks.",
  },
  {
    icon: Activity,
    title: "Eight independent detectors",
    body: "Temporal, semantic, AI-writing, voice, engagement, profile, memory, and coordination detectors each emit a calibrated probability — never a binary verdict.",
  },
  {
    icon: Network,
    title: "Coordination signals",
    body: "Six cross-account detectors surface clusters acting in concert: shared timing, matching fingerprints, reply pods, co-engagement, age cohorts, and style matches.",
  },
  {
    icon: Brain,
    title: "OmiScore intelligence",
    body: "Detector outputs compose into one explainable envelope — authenticity, coordination, amplification, spam, and AI-generation probabilities — each score traceable to the evidence behind it.",
  },
  {
    icon: Eye,
    title: "Narrative tracking",
    body: "Comments are embedded and clustered so you can watch talking points propagate and mutate across sections in real time.",
  },
  {
    icon: GitBranch,
    title: "A self-improving engine",
    body: "Every scan adds to a persistent fingerprint memory. The more OmiSphere observes, the sharper its priors become — intelligence that compounds.",
  },
];

export default function AboutPage() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      {/* Ambient backdrop */}
      <div className="pointer-events-none absolute inset-0 bg-grid-faint bg-[size:64px_64px] opacity-[0.12]" />
      <div className="pointer-events-none absolute left-1/2 top-[-10rem] h-[36rem] w-[52rem] -translate-x-1/2 rounded-full bg-primary/15 blur-[140px] animate-aurora" />

      <div className="relative z-10 mx-auto max-w-5xl px-6 py-10">
        {/* Nav */}
        <div className="mb-16 flex items-center justify-between">
          <Logo />
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft size={15} /> Back
          </Link>
        </div>

        {/* Header */}
        <div className="mx-auto max-w-2xl text-center">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/10 bg-card/50 px-4 py-1.5 text-xs text-muted-foreground backdrop-blur">
            How it works
          </div>
          <h1 className="text-balance text-4xl font-bold leading-tight tracking-tight md:text-5xl">
            Authenticity intelligence,{" "}
            <span className="text-gradient">end to end</span>.
          </h1>
          <p className="mt-5 text-pretty text-lg text-muted-foreground">
            OmiSphere doesn&apos;t guess. It measures observable behavior, layers
            independent signals, and reports calibrated probabilities you can
            trace back to evidence — so you can tell who&apos;s real and who&apos;s not.
          </p>
        </div>

        {/* Layers */}
        <div className="mt-16 grid gap-5 md:grid-cols-2">
          {LAYERS.map((l) => (
            <div
              key={l.title}
              className="ring-gradient group relative overflow-hidden rounded-2xl bg-card/40 p-6 backdrop-blur transition-all duration-300 hover:-translate-y-1 hover:bg-card/70"
            >
              <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-background/60">
                <l.icon className="text-primary" size={20} />
              </div>
              <h3 className="mb-2 font-semibold">{l.title}</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">{l.body}</p>
            </div>
          ))}
        </div>

        {/* Principle */}
        <div className="ring-gradient relative mt-16 overflow-hidden rounded-3xl bg-gradient-to-br from-card to-card/20 p-10 text-center">
          <div className="pointer-events-none absolute inset-0 bg-brand-radial opacity-50" />
          <div className="relative z-10 mx-auto max-w-2xl">
            <h2 className="text-2xl font-bold md:text-3xl">Probabilities, not accusations</h2>
            <p className="mt-4 text-muted-foreground">
              Every output is a calibrated estimate with its confidence and
              supporting evidence attached — a probabilistic read on observable
              patterns, never a definitive judgement about the person behind an
              account.
            </p>
            <Link
              href="/signup"
              className="mt-8 inline-flex items-center gap-2 rounded-lg bg-brand-gradient px-6 py-3 font-medium text-primary-foreground glow-primary"
            >
              Start investigating
            </Link>
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-16 border-t border-border pt-8 text-center text-sm text-muted-foreground">
          © 2026 OmiSphere. Authenticity intelligence.
        </footer>
      </div>
    </div>
  );
}
