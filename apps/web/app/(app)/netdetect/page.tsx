import { notFound } from 'next/navigation';
import { apiServer } from '@/lib/api-server';
import { type User } from '@/lib/api';
import { FindingQueue } from './finding-queue';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

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
      />

      <FindingQueue />
    </div>
  );
}
