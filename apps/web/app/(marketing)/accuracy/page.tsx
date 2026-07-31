export const metadata = {
  title: 'Accuracy and scope. OMISPHERE',
  description:
    'What an OMISPHERE score is, what it is not, how it can be wrong, and how to have a report reviewed.',
};

/**
 * The accuracy and scope statement.
 *
 * This exists because the product publishes scored claims about named, identifiable accounts whose
 * owners never agreed to be analysed, and those reports get shared publicly. Anyone who lands on a
 * report, including the person it is about, needs to be able to read exactly what the number means,
 * what it does not mean, and how to contest it. Linked from every public report.
 *
 * Written to be read by a person who has just found themselves scored and is upset about it. That is
 * the audience that matters most here, and the tone should not be defensive.
 */
export default function AccuracyPage() {
  return (
    <article className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">
          Scope and limits
        </p>
        <h1 className="text-3xl font-semibold text-fg tracking-tight">Accuracy and scope</h1>
        <p className="mt-1 font-mono text-2xs text-fg-mute">Last updated: July 2026</p>
      </header>

      <p className="text-fg-dim leading-relaxed">
        OMISPHERE produces a score, from 0 to 100, describing how closely an account&apos;s public
        behaviour resembles patterns associated with bought, automated, or engagement-farming
        activity. This page explains what that number is, what it is not, and what to do if you
        believe a report is wrong about you.
      </p>

      <Callout>
        A score is a probabilistic reading of public behaviour. It is not a finding of fact, not an
        accusation, and not evidence that any person has done anything wrong.
      </Callout>

      <Section title="What we are actually claiming">
        Every score is a measurement of observable patterns in public data: when an account posts,
        whether its text repeats, how its follower and following counts relate, how much history it
        has, and what its posts say. We report what those patterns resemble. We are not asserting that
        an account is a bot, that anyone was paid, or that any rule or law has been broken. We publish
        these readings so that patterns in public conversation can be examined openly rather than
        guessed at.
      </Section>

      <Section title="What we are not claiming">
        We make no claim about who owns or operates an account, whether money changed hands, whether
        an account belongs to any organisation or campaign, or what anyone intended. None of that is
        in the data we analyse, and any report that reads as though it were should be reported to us
        using the link on it.
      </Section>

      <Section title="Scores can be wrong, in both directions">
        This is automated analysis and it makes mistakes. A high score can be produced by an account
        that is entirely genuine, and a low score does not certify that an account is authentic. Some
        ordinary account types resemble the patterns we look for, including:
        <ul className="mt-3 space-y-1.5 list-disc pl-5">
          <li>businesses, brands, shops, and creators, whose posting is promotional by nature</li>
          <li>fan, hobby, and supporter accounts, which are repetitive and enthusiastic by nature</li>
          <li>news, sports, and aggregator accounts, which post on a schedule</li>
          <li>people who genuinely just joined, and so have few followers, few posts, and no bio</li>
          <li>accounts that were dormant and became active again</li>
          <li>private individuals with a small footprint, which is most people</li>
          <li>
            people writing in a second language or a non-Latin script, whose phrasing and handles can
            superficially resemble automated text
          </li>
        </ul>
        <p className="mt-3">
          Our analysis is instructed to recognise these and to require several independent indicators
          before returning a high score. It still gets things wrong, which is why the review process
          below exists.
        </p>
      </Section>

      <Section title="How to read a report">
        Treat a score as a starting point for your own judgement, not a conclusion. The written note
        beside each account is meant to name the specific, checkable facts behind the number, so that
        you can go and look at the account yourself and disagree with us. If a report makes a claim
        you cannot verify against the account it describes, that is a defect and we want to hear about
        it.
      </Section>

      <Section title="If you are named in a report">
        Every public report carries a &ldquo;Request a review&rdquo; link. Use it. You do not need an
        account with us, and you do not need to explain who you are. Tell us which account the report
        names and what it gets wrong, and a person will check it against the evidence the score was
        based on.
        <p className="mt-3">
          We can and do withdraw published reports. A report that we cannot stand up is removed, and
          the public link stops working immediately.
        </p>
      </Section>

      <Section title="Data we analyse">
        We analyse information that is already public on the platform: profile metadata, public posts,
        and public comments. We do not access private messages, private accounts, deleted content, or
        anything behind a login that is not our own. See our{' '}
        <a href="/privacy" className="text-accent hover:underline">
          privacy policy
        </a>{' '}
        for what we retain and your rights over it.
      </Section>

      <Section title="Reporting a problem">
        If a report is inaccurate, misleading, or being used to harass someone, tell us. Use the
        review link on the report itself, which reaches us fastest because it carries the report
        reference, or write to{' '}
        <a href="mailto:privacy@omisphere.ai" className="text-accent hover:underline">
          privacy@omisphere.ai
        </a>
        .
      </Section>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-lg font-semibold text-fg mb-2">{title}</h2>
      <div className="text-fg-dim leading-relaxed">{children}</div>
    </section>
  );
}

function Callout({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-accent/30 bg-accent/[0.06] p-4">
      <p className="text-sm text-fg leading-relaxed">{children}</p>
    </div>
  );
}
