export const metadata = { title: 'Terms — OMISPHERE' };

export default function TermsPage() {
  return (
    <article className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">Legal</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Terms of Service</h1>
        <p className="mt-1 font-mono text-2xs text-fg-mute">Last updated: May 2026</p>
      </header>

      <p className="text-fg-dim leading-relaxed">
        These terms govern your use of OMISPHERE. By creating an account or using
        the service, you agree to them. If you do not agree, do not use the
        service.
      </p>

      <Section title="The service">
        OMISPHERE analyzes publicly available social-media activity and returns
        probabilistic authenticity and coordination signals. The product is under
        active development; features may change, and we may impose reasonable
        limits to keep the service stable and within third-party API quotas.
      </Section>

      <Section title="Your account">
        You are responsible for keeping your login credentials secure and for all
        activity under your account. Provide accurate information, and notify us
        promptly if you believe your account has been compromised.
      </Section>

      <Section title="Credits and billing">
        Scans are metered in credits. New accounts receive a limited number of
        free trial credits. Paid subscriptions are billed monthly through Stripe
        and grant a fixed number of credits per billing month; unused credits do
        not roll over. You can cancel anytime from your account settings;
        cancellation takes effect at the end of the current billing month. Except
        where required by law, payments are non-refundable and we do not pro-rate
        partial months.
      </Section>

      <Section title="What OMISPHERE's output is — and is not">
        All output is <strong>probabilistic</strong> and provided{' '}
        <strong>for research and informational purposes only</strong>. Scores are
        statistical estimates based on observable patterns. They are never a
        definitive judgement about an account or the person behind it. You agree
        not to present OMISPHERE&apos;s output as proof of anyone&apos;s identity,
        intent, or affiliation, and not to use it to make decisions that produce
        legal or similarly significant effects about a person without independent
        human review.
      </Section>

      <Section title="Acceptable use">
        You agree not to use OMISPHERE to harass, dox, surveil, or target
        individuals; to violate the terms of service of any social platform or
        the YouTube API Terms; to bypass rate limits or quotas; to scrape or
        resell the service or its output; or to break any applicable law. We may
        suspend or terminate accounts that abuse the service.
      </Section>

      <Section title="Intellectual property">
        OMISPHERE, including the omi detection engine and the interface, is our
        property. You retain ownership of the inputs you submit; you grant us the
        limited rights needed to operate the service, including computing and
        retaining de-identified detection signals as described in our Privacy
        Policy.
      </Section>

      <Section title="Disclaimer and limitation of liability">
        OMISPHERE&apos;s output is provided &quot;as is&quot; and &quot;as
        available,&quot; without warranties of any kind, express or implied. You
        are solely responsible for any decisions or actions you take based on it.
        To the maximum extent permitted by law, we are not liable for any
        indirect, incidental, or consequential damages, and our total liability
        for any claim is limited to the amount you paid us in the three months
        before the claim arose.
      </Section>

      <Section title="Indemnification">
        You agree to indemnify and hold OMISPHERE harmless from claims arising out
        of your use of the service or your violation of these terms.
      </Section>

      <Section title="Termination">
        You may stop using the service and delete your account at any time. We may
        suspend or terminate access for violations of these terms or to comply
        with the law.
      </Section>

      <Section title="Changes">
        We may update these terms as the product evolves. Material changes will be
        reflected in the &ldquo;last updated&rdquo; date above; continued use after
        a change means you accept the updated terms.
      </Section>

      <Section title="Contact">
        Questions about these terms? Email{' '}
        <a href="mailto:support@omisphere.ai" className="text-accent hover:text-accent-2">
          support@omisphere.ai
        </a>
        .
      </Section>

      <p className="font-mono text-2xs text-fg-mute mt-8 italic">
        These terms are written in plain language and reflect how the service
        currently operates. They are not legal advice.
      </p>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-accent mb-2 mt-6">{title}</h2>
      <div className="text-fg-dim leading-relaxed">{children}</div>
    </section>
  );
}
