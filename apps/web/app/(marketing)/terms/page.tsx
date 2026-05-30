export const metadata = { title: 'Terms — OMISPHERE' };

export default function TermsPage() {
  return (
    <article className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">Legal</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Terms of Service</h1>
        <p className="mt-1 font-mono text-2xs text-fg-mute">Last updated: 2026</p>
      </header>

      <Section title="What you're buying">
        Each subscription month entitles you to a fixed number of comprehensive scans.
        Unused scans expire at the end of the billing month.
      </Section>

      <Section title="What OMISPHERE's output is">
        All output is <strong>probabilistic</strong> and <strong>for research purposes only</strong>.
        Scores are statistical estimates based on observable patterns. They are never a definitive
        judgement about an account or the person behind it. You agree not to present
        OMISPHERE&apos;s output as proof of anyone&apos;s identity, intent, or affiliation.
      </Section>

      <Section title="Acceptable use">
        You agree not to use OMISPHERE to harass, dox, or target individuals; to violate
        the terms of service of any social platform; or to attempt to bypass rate limits
        or quotas.
      </Section>

      <Section title="Refunds">
        Subscriptions are billed monthly and can be canceled at any time from your account.
        Cancellation takes effect at the end of the current billing month. We do not offer
        pro-rated refunds for partial months.
      </Section>

      <Section title="Liability">
        OMISPHERE&apos;s output is provided &quot;as is&quot; with no warranty. You are solely responsible
        for any decisions or actions you take based on OMISPHERE&apos;s output.
      </Section>

      <p className="font-mono text-2xs text-fg-mute mt-8 italic">
        Placeholder. Replace with lawyer-reviewed terms before going live with real billing.
      </p>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-accent mb-2 mt-6">{title}</h2>
      <p className="text-fg-dim leading-relaxed">{children}</p>
    </section>
  );
}
