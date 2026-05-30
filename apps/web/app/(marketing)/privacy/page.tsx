export const metadata = { title: 'Privacy — OMISPHERE' };

export default function PrivacyPage() {
  return (
    <article className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">Legal</p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Privacy Policy</h1>
        <p className="mt-1 font-mono text-2xs text-fg-mute">Last updated: 2026</p>
      </header>

      <Section title="What we collect">
        <ul className="list-disc list-inside space-y-1">
          <li>Your account email (for login and billing receipts)</li>
          <li>A hashed password (we never see your real password)</li>
          <li>A log of scans you&apos;ve run (to track credit usage and improve detection)</li>
          <li>Payment information is handled exclusively by Stripe; we never see card details</li>
        </ul>
      </Section>

      <Section title="What we do with public social-media data">
        When you scan a YouTube channel or video, OMISPHERE retrieves publicly available
        data via the YouTube Data API: channel metadata, comment text, and creation
        timestamps. We compute behavioral fingerprints from this data and store them to
        improve future scans. We do not publish scan results. We do not sell or share
        your scan history with third parties.
      </Section>

      <Section title="Data retention">
        Behavioral fingerprints are retained indefinitely (this is the core value of
        OMISPHERE&apos;s self-improving database). You can request deletion of your account
        and personal scan history at any time by contacting us.
      </Section>

      <Section title="Third parties">
        Stripe (payments), Render (hosting), Supabase (database). No other third parties
        receive your data.
      </Section>

      <p className="font-mono text-2xs text-fg-mute mt-8 italic">
        Placeholder. Replace with lawyer-reviewed policy reflecting your actual data
        practices and applicable jurisdictions (GDPR, CCPA, etc.) before going live.
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
