import { Shield, Database, Cpu, GitBranch, Scale } from 'lucide-react';
import { Card } from '@/components/ui/card';

export const metadata = { title: 'About. OMISPHERE' };

const SECTIONS = [
  {
    icon: Shield,
    title: 'What OMISPHERE is not',
    body: (
      <>
        OMISPHERE is <strong className="text-fg">not a binary &ldquo;bot / not-bot&rdquo; classifier</strong>. Every
        result is a probability with an explicit evidence chain. We never accuse, we
        never claim certainty, and we never tell you a person is a bot. We tell you
        that certain observable patterns are consistent with synthetic or coordinated
        behavior, and we show you exactly what those patterns are.
      </>
    ),
  },
  {
    icon: Database,
    title: 'Self-improving',
    body: (
      <>
        Every scan adds a behavioral fingerprint to OMISPHERE&apos;s database. Future scans
        pull priors from that growing set. The platform sharpens with every use, and
        the intelligence belongs to its users collectively.
      </>
    ),
  },
  {
    icon: Cpu,
    title: 'The omi detection engine',
    body: (
      <>
        Under the hood, the detection engine is called{' '}
        <span className="mono text-accent">omi</span>. It runs locally with
        no LLM calls in the per-scan path. Pure Python heuristics, embeddings, and
        graph algorithms. LLMs are reserved for optional report generation, never the
        core scoring.
      </>
    ),
  },
  {
    icon: GitBranch,
    title: 'Scope, plainly',
    body: (
      <>
        Today OMISPHERE scans <span className="text-fg">YouTube</span> only. Videos
        and channels. Every &ldquo;scan&rdquo; covers a video&apos;s comment thread or a
        single channel&apos;s recent activity, and consumes one credit. X / Twitter
        ingestion is the next platform on the roadmap; pricing for X scans will
        reflect that platform&apos;s higher API cost when it ships.
      </>
    ),
  },
  {
    icon: Scale,
    title: 'Ethical use',
    body: (
      <>
        OMISPHERE is for researchers, journalists, brand-safety teams, and
        platform-integrity professionals. It is not a tool to harass individuals.
        Probabilistic patterns are not proof.
      </>
    ),
  },
];

export default function AboutPage() {
  return (
    <article className="space-y-10">
      <header>
        <span className="section-label mb-3">About</span>
        <h1 className="display text-3xl md:text-4xl font-semibold tracking-tight leading-tight mt-3">
          Purpose-built bot detection.{' '}
          <span className="text-brand">Not a wrapper around a chatbot.</span>
        </h1>
        <p className="mt-4 text-fg-dim leading-relaxed">
          OMISPHERE scores the accounts in a comment section: how likely each
          one is bought, farmed, or automated rather than a real person, on
          YouTube and X (Twitter). Every finding is a probability with its
          confidence, the evidence for it, the evidence against it, and a plain
          English explanation of why the account scored the way it did. Built
          for OSINT researchers, investigative journalists, and
          trust-&amp;-safety teams.
        </p>
      </header>

      <div className="space-y-4 stagger">
        {SECTIONS.map(({ icon: Icon, title, body }) => (
          <Card key={title} interactive>
            <div className="flex gap-4">
              <div className="shrink-0 w-10 h-10 rounded-md bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent">
                <Icon size={18} />
              </div>
              <div>
                <h2 className="text-base font-semibold text-fg mb-1.5">{title}</h2>
                <div className="text-sm text-fg-dim leading-relaxed">{body}</div>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Platform roadmap. Relocated from the dashboard: "what's coming" is
          marketing context, not workspace content. */}
      <Card>
        <h2 className="text-base font-semibold text-fg mb-1.5">Platform roadmap</h2>
        <p className="text-sm text-fg-dim mb-4">
          Depth over breadth. Deep coordination intelligence on the platforms
          that matter most.
        </p>
        <ul className="space-y-2 text-sm">
          <li className="flex gap-3"><span className="font-mono text-accent shrink-0">✓</span><span><span className="text-fg font-medium">YouTube</span> <span className="text-fg-dim">, live: full comment analysis, per-account scoring, channel intelligence</span></span></li>
          <li className="flex gap-3"><span className="font-mono text-accent shrink-0">✓</span><span><span className="text-fg font-medium">X / Twitter</span> <span className="text-fg-dim">, live: per-account scoring, account fingerprinting, posting-history analysis</span></span></li>
          <li className="flex gap-3"><span className="font-mono text-fg-faint shrink-0">○</span><span><span className="text-fg font-medium">Reddit</span> <span className="text-fg-dim">, coming soon November 1st: post + comment analysis</span></span></li>
          <li className="flex gap-3"><span className="font-mono text-fg-faint shrink-0">○</span><span><span className="text-fg font-medium">TikTok</span> <span className="text-fg-dim">, coming soon November 1st: comment-section analysis, creator audience intelligence</span></span></li>
        </ul>
      </Card>
    </article>
  );
}
