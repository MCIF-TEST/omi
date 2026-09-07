import { notFound } from 'next/navigation';
import { Card } from '@/components/ui/card';
import { apiServer } from '@/lib/api-server';
import { type User } from '@/lib/api';
import { CoordinationQueue } from './coordination-queue';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';
import { CoordinationNav, WhyTwoDetectors } from '@/components/shared/coordination-nav';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Coordination' };

/**
 * The coordinated-campaign queue.
 *
 * ADMIN ONLY, and gated on the SERVER. Hiding the nav item would not be enough, because the route
 * would still answer to anyone who typed the URL, and `adminOnly` in the nav files is presentation
 * only. `force-dynamic` so a cached render cannot serve one user's gate result to another.
 *
 * Admin-only is a product decision, not a technicality. The detector's thresholds are reasoned
 * rather than fitted against a labelled corpus, and it names groups of real people, so a finding is
 * an operator's lead to review before anything is said publicly. Nothing here reaches the customer
 * app, the shared report, or the exports.
 */
export default async function NarrativesPage() {
  let user: User | null = null;
  try {
    user = await apiServer<User>('/v1/auth/me');
  } catch {
    user = null;
  }
  if (!user?.is_admin) notFound();

  return (
    <div className="space-y-6 max-w-4xl">
      <ConsoleHeader
        index={SECTION_INDEX['/narratives']}
        eyebrow="Coordination · Admin"
        title="Coordinated campaigns"
        lede="Accounts an investigation scored at 70 or above, grouped by evidence they produced themselves. Runs on every scan, costs nothing, and calls no model."
      >
        {/* The same rail as the other two coordination surfaces. Three pages answering one question
            in three vocabularies, with no way to get between them, is most of why they read as
            three unrelated tools rather than one. */}
        <CoordinationNav current="/narratives" />
      </ConsoleHeader>

      <CoordinationQueue />

      {/* Stated here rather than buried in a docstring. An operator reading a finding needs to know
          what the method cannot see, or "no coordination found" gets read as "these accounts are
          unrelated", which is a different and much stronger claim. */}
      <Card className="space-y-2">
        <span className="section-label">What this catches</span>
        <p className="text-sm text-fg-dim leading-relaxed">
          Operations that reuse copy, arrive in lockstep against the thread&apos;s own rate, share a
          non-standard posting tool, keep turning up at the same unpopular posts, or were
          provisioned in one batch. A group needs at least two independent kinds of evidence before
          it is called a campaign; one kind alone is held at 49% however strong it looks.
        </p>
        <p className="text-sm text-fg-dim leading-relaxed">
          It will not catch a well-run operation using aged accounts with individually written
          posts on ordinary clients. Five of the seven signals go quiet against that, so an empty
          result means no mechanical tell was found, not that the accounts are unrelated.
        </p>
        <p className="text-sm text-fg-mute leading-relaxed">
          Every finding is an observation about behaviour that co-occurred. It is not a claim about
          who operates an account, whether money changed hands, or anyone&apos;s intent.
        </p>
        {/* The blind spot this page has and the other one does not, stated on the page it applies
            to. The 70 cut is measured to be a cliff rather than a slope: one point under it and a
            whole operation leaves this pass entirely, and the cohort comes back EMPTY rather than
            incomplete, so nothing here records that anything was skipped. */}
        <WhyTwoDetectors />
      </Card>
    </div>
  );
}
