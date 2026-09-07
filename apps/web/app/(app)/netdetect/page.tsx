import { notFound } from 'next/navigation';
import { apiServer } from '@/lib/api-server';
import { type User } from '@/lib/api';
import { FindingQueue } from './finding-queue';
import { UnresolvedSections } from './unresolved-sections';
import { FormationCatalogue } from './formation-catalogue';
import { FormationSweep } from './formation-sweep';
import { RunPanel } from './run-panel';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';
import { CoordinationNav, WhyTwoDetectors } from '@/components/shared/coordination-nav';
import { Stage } from '@/components/shared/stage-rail';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Network findings' };

/**
 * The network detector's finding queue.
 *
 * `/v1/admin/netdetect/*` has existed since findings became persistent, and with no interface the
 * only way to read or judge one was curl. That matters more here than it looks: every threshold in
 * `app/netdetect` is reasoned rather than fitted, because no labelled corpus of coordinated accounts
 * exists and none can be bought, and the calibration report deliberately refuses to recommend
 * anything until thirty findings have been judged with at least eight of each class. Nobody produces
 * thirty judgements through curl, so the ground-truth path was inert without this page.
 *
 * ADMIN ONLY, gated on the SERVER, and `force-dynamic` so a cached render cannot serve one user's
 * gate result to another. A finding names real people as running an operation together on
 * statistical evidence; the queue carries other customers' investigation ids; and there is no owner
 * to scope any of it to, which is the same reason `/campaigns` and `/narratives` are gated. Hiding
 * the nav link alone would leave the route answering to anyone who typed the URL. The API re-checks
 * on every route, which is what actually protects the data.
 */
export default async function NetdetectPage() {
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
        index={SECTION_INDEX['/netdetect']}
        eyebrow="Operations · Admin"
        title="Network findings"
        lede="Sets of accounts that share improbably many rare behaviours, corrected for the size of the search. A finding is a lead, not a verdict: judging one records the only ground truth this detector will ever accumulate, and nothing here reaches a customer."
      >
        <CoordinationNav current="/netdetect" />
      </ConsoleHeader>

      {/* THE JOB HAS AN ORDER, AND SAYING SO IS MOST OF THE FIX. These panels were stacked in a
          column with nothing to say which came first or that they were one piece of work. Each was
          individually legible and the page as a whole was not: an operator could tell what every
          panel showed and not what to do with it. */}

      <Stage
        n={1}
        title="Run the detector"
        lede="Pick a scan you have already run. Detection re-reads stored evidence, so it costs nothing and can be run as often as you like."
      >
        <RunPanel />
        {/* ABOVE the queue, because it is a warning about what a queue can never contain. A section
            one group is large enough to dominate produces NO findings at all, which reads exactly
            like a clean scan, so it belongs where a run happens rather than being left for somebody
            to notice its absence. */}
        <UnresolvedSections />
      </Stage>

      <Stage
        n={2}
        title="Review what it found"
        lede="Each finding names real accounts on statistical evidence. Confirming or dismissing one records the only ground truth this detector will ever have, which is what lets its thresholds be calibrated at all."
      >
        <FindingQueue />
      </Stage>

      <Stage
        n={3}
        title="Track what you confirmed"
        lede="An operation persists across posts and survives its accounts being burned and replaced. Sweep a new comment section against everything catalogued here."
      >
        <FormationCatalogue />
        <FormationSweep />
      </Stage>

      <WhyTwoDetectors className="sm:pl-9" />
    </div>
  );
}
