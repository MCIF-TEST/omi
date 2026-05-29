export const metadata = { title: 'About — OMISPHERE' };

export default function AboutPage() {
  return (
    <article className="prose-section space-y-8">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">About</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">
          A trust layer for YouTube comment sections
        </h1>
        <p className="mt-3 text-fg-dim leading-relaxed">
          OMISPHERE is a probabilistic intelligence platform for YouTube comments. It
          detects bot accounts, AI-generated engagement, coordinated influence
          campaigns, engagement farms, and synthetic virality — using eight
          independent detectors and a self-improving fingerprint database. The
          detection engine is platform-agnostic by design; today the only
          ingestion adapter shipped is YouTube. Other platforms are on the roadmap.
        </p>
      </header>

      <Section title="What OMISPHERE is not">
        <p>
          OMISPHERE is <strong>not a binary "bot / not-bot" classifier</strong>. Every
          result is a probability with an explicit evidence chain. We never accuse, we
          never claim certainty, and we never tell you a person is a bot. We tell you
          that certain observable patterns are consistent with synthetic or coordinated
          behavior — and we show you exactly what those patterns are.
        </p>
      </Section>

      <Section title="Self-improving">
        <p>
          Every scan adds a behavioral fingerprint to OMISPHERE's database. Future scans
          pull priors from that growing set. The platform sharpens with every use — and
          the intelligence belongs to its users collectively.
        </p>
      </Section>

      <Section title="The omi detection engine">
        <p>
          Under the hood, the detection engine is called <span className="mono text-accent">omi</span>. It runs locally with
          no LLM calls in the per-scan path — pure Python heuristics, embeddings, and
          graph algorithms. LLMs are reserved for optional report generation, never the
          core scoring.
        </p>
      </Section>

      <Section title="Scope, plainly">
        <p>
          Today OMISPHERE scans <span className="text-fg">YouTube</span> only — videos
          and channels. Every &ldquo;scan&rdquo; covers a video&apos;s comment thread or a
          single channel&apos;s recent activity, and consumes one credit. X / Twitter
          ingestion is the next platform on the roadmap; pricing for X scans will
          reflect that platform&apos;s higher API cost when it ships.
        </p>
      </Section>

      <Section title="Ethical use">
        <p>
          OMISPHERE is for researchers, journalists, brand-safety teams, and
          platform-integrity professionals. It is not a tool to harass individuals.
          Probabilistic patterns are not proof.
        </p>
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-accent mb-2 mt-8">{title}</h2>
      <div className="text-fg-dim leading-relaxed">{children}</div>
    </section>
  );
}
