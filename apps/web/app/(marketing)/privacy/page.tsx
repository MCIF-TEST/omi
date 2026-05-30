export const metadata = { title: 'Privacy — OMISPHERE' };

export default function PrivacyPage() {
  return (
    <article className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">Legal</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Privacy Policy</h1>
        <p className="mt-1 font-mono text-2xs text-fg-mute">Last updated: May 2026</p>
      </header>

      <p className="text-fg-dim leading-relaxed">
        This policy explains what OMISPHERE collects, why, and the choices you
        have. OMISPHERE is a tool for analyzing publicly available social-media
        activity; we have designed it to collect as little personal data about
        <em> you</em> as possible.
      </p>

      <Section title="Account data we collect">
        <ul className="list-disc list-inside space-y-1">
          <li>Your email address — for login, account recovery, and billing receipts.</li>
          <li>
            A one-way <span className="font-mono">bcrypt</span> hash of your
            password. We never store or see your actual password.
          </li>
          <li>A log of the scans you run, used to meter credits and bill accurately.</li>
          <li>
            A one-way hash of the IP address you signed up from, used solely to
            detect free-trial abuse. We do not store your raw IP address.
          </li>
          <li>Your referral code and, if you were referred, who referred you.</li>
          <li>
            Your notification preferences and, if you set one, an outbound
            webhook URL.
          </li>
          <li>
            Payment details are handled exclusively by Stripe. We never receive
            or store your card number.
          </li>
        </ul>
      </Section>

      <Section title="Public social-media data we process">
        When you scan a YouTube channel or video, OMISPHERE retrieves publicly
        available data through the YouTube Data API: channel metadata, comment
        text, public engagement counts, and creation timestamps. From this we
        compute behavioral fingerprints and coordination signals. We only
        process data that is already public; we do not access private messages,
        non-public account details, or anything behind a login.
      </Section>

      <Section title="How we use data">
        <ul className="list-disc list-inside space-y-1">
          <li>To run detections and present results to you.</li>
          <li>
            To improve accuracy over time. Behavioral fingerprints derived from
            scans feed a shared detection database — the core of how OMISPHERE
            gets smarter as more content is analyzed.
          </li>
          <li>To meter credits, process subscriptions, and prevent abuse.</li>
          <li>To deliver the alerts and notifications you opt into.</li>
        </ul>
      </Section>

      <Section title="Cookies">
        We use a single, signed, httpOnly session cookie to keep you logged in.
        We do not use advertising cookies, third-party trackers, or
        cross-site analytics.
      </Section>

      <Section title="Sharing and subprocessors">
        We do not sell your data and we do not share your scan history with
        third parties for their own purposes. We rely on a small set of
        subprocessors to operate the service: Stripe (payments), our hosting
        and managed-database providers (application + storage), an optional SMTP
        provider (alert and account emails), and — only when you explicitly
        generate analyst commentary on an investigation — Anthropic&apos;s API
        for that single request.
      </Section>

      <Section title="Your rights">
        You can request access to, export of, or deletion of your account and
        associated personal data at any time. Deleting your account removes your
        login, scan logs, saved investigations, watchlists, and graphs.
        Aggregated, de-identified detection signals that do not identify you may
        be retained as part of the shared detection database. To exercise any of
        these rights, email{' '}
        <a href="mailto:privacy@omisphere.ai" className="text-accent hover:text-accent-2">
          privacy@omisphere.ai
        </a>
        .
      </Section>

      <Section title="Data retention">
        Account data is kept for as long as your account is active and deleted on
        request. De-identified behavioral fingerprints may be retained
        indefinitely as part of the detection dataset.
      </Section>

      <Section title="Security">
        Passwords are hashed with bcrypt, sessions are signed and httpOnly, and
        traffic is served over TLS in production. No system is perfectly secure,
        but we work to protect your data and to minimize what we hold.
      </Section>

      <Section title="Children">
        OMISPHERE is not intended for anyone under 16, and we do not knowingly
        collect data from children.
      </Section>

      <Section title="Changes">
        We may update this policy as the product evolves. Material changes will
        be reflected in the &ldquo;last updated&rdquo; date above.
      </Section>

      <Section title="Contact">
        Questions about privacy? Email{' '}
        <a href="mailto:privacy@omisphere.ai" className="text-accent hover:text-accent-2">
          privacy@omisphere.ai
        </a>
        .
      </Section>

      <p className="font-mono text-2xs text-fg-mute mt-8 italic">
        This policy describes our current data practices in plain language. It is
        not legal advice. If your use is governed by a specific regime (GDPR,
        CCPA, or another), contact us with any questions.
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
