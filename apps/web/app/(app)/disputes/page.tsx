import { notFound } from 'next/navigation';
import { apiServer } from '@/lib/api-server';
import { type User } from '@/lib/api';
import { DisputeQueue } from './dispute-queue';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Disputes · OMISPHERE' };

/**
 * The dispute queue.
 *
 * `POST /r/<token>/dispute` has existed since the report-disputes change, but with no interface the
 * only way to read it was curl. That is not a takedown process: the whole value of the route is that
 * an operator can say "reviewed and acted within a day" instead of "there was no way to reach us",
 * and a queue nobody can see cannot deliver that. These are time-sensitive complaints from people who
 * never agreed to be scored, and some of them will arrive with a lawyer's letterhead.
 *
 * ADMIN ONLY, gated on the SERVER, for two reasons rather than one: the queue holds complainants'
 * contact details, and the resolve route can unpublish ANY report in the system. Hiding the nav link
 * would leave the route answering to anyone who typed the URL, so the page itself is the access
 * control (the API re-checks too, which is what actually protects the data).
 */
export default async function DisputesPage() {
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
        index={SECTION_INDEX['/disputes']}
        eyebrow="Operations · Admin"
        title="Report disputes"
        lede="People who believe a published report is wrong about them file here, without an account. Filing does not unpublish anything on its own. Taking a report down is a decision made on this page, and it works on any report, not only your own."
      />

      <DisputeQueue />
    </div>
  );
}
