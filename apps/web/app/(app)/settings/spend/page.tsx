import Link from 'next/link';
import { redirect } from 'next/navigation';
import { ArrowLeft, Wallet } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import { type UpstreamUsageSnapshot } from '@/lib/api';

export const metadata = { title: 'Upstream spend. OMISPHERE' };
export const dynamic = 'force-dynamic';

/**
 * What today's scanning cost, against the daily ceilings.
 *
 * The compile step charges no credits and calls an API that bills per read, so credits cannot guard
 * it. The ceilings in app/core/upstream_budget.py stop a runaway; this page is the half that lets
 * anyone notice one building. A budget with no readout only ever tells you that you were refused,
 * never how close you are, which user is heavy, or whether today is normal.
 *
 * Admin only, gated on the server: it exposes per-user activity volumes.
 */
export default async function SpendPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) {
    redirect('/settings');
  }

  const usage = await apiServer<UpstreamUsageSnapshot>('/v1/admin/usage').catch(() => null);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 meta meta-hi hover:text-fg-dim"
        >
          <ArrowLeft size={13} /> Settings
        </Link>
        <h1 className="display-hard-sm text-2xl mt-3">Upstream spend</h1>
        <p className="text-sm text-fg-dim mt-1.5 max-w-2xl leading-relaxed">
          Calls made to the paid platform APIs. This is the number that bills, not the number of
          requests the product served: one compile can page the provider several times.
        </p>
      </div>

      {!usage ? (
        <Card>
          <p className="text-sm text-fg-dim">
            The spend ledger could not be read. The API may be restarting.
          </p>
        </Card>
      ) : (
        <>
          <Card>
            <CardLabel>Today · {usage.date} UTC</CardLabel>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <Figure label="API calls" value={usage.today_api_calls.toLocaleString()} />
              <Figure
                label="Deployment budget"
                value={usage.global_budget > 0 ? usage.global_budget.toLocaleString() : 'off'}
              />
              <Figure
                label="Remaining"
                value={
                  usage.global_remaining === null
                    ? 'unlimited'
                    : usage.global_remaining.toLocaleString()
                }
                tone={
                  usage.global_remaining !== null &&
                  usage.global_budget > 0 &&
                  usage.global_remaining < usage.global_budget * 0.15
                    ? 'bad'
                    : 'neutral'
                }
              />
            </div>
            <p className="text-xs text-fg-mute mt-4 leading-relaxed">
              Per user, per day: {usage.per_user_budget > 0 ? usage.per_user_budget.toLocaleString() : 'no limit'}.
              Both ceilings are env-tunable (OMI_UPSTREAM_DAILY_CALLS_PER_USER,
              OMI_UPSTREAM_DAILY_CALLS_GLOBAL) so a spike is absorbed without a deploy. The
              deployment ceiling refuses paying customers when it trips, so treat it as a circuit
              breaker to raise, not a business limit.
            </p>
          </Card>

          {usage.by_platform.length > 0 && (
            <Card>
              <CardTitle>By platform, today</CardTitle>
              <div className="space-y-1.5 mt-3">
                {usage.by_platform.map((p) => (
                  <Row key={p.platform} left={p.platform} right={p.api_calls.toLocaleString()} />
                ))}
              </div>
            </Card>
          )}

          <Card>
            <CardTitle>Recent days</CardTitle>
            {usage.by_day.length === 0 ? (
              <p className="text-sm text-fg-dim mt-2">Nothing recorded yet.</p>
            ) : (
              <div className="space-y-1.5 mt-3">
                {usage.by_day.map((d) => (
                  <Row
                    key={d.date}
                    left={d.date}
                    right={`${d.api_calls.toLocaleString()} calls · ${d.requests.toLocaleString()} requests`}
                  />
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardTitle>Heaviest today</CardTitle>
            <p className="text-xs text-fg-mute mt-1">
              Where the day went. &quot;anon&quot; is the pre-login demo, which every visitor shares.
            </p>
            {usage.heaviest_users_today.length === 0 ? (
              <p className="text-sm text-fg-dim mt-3">Nothing recorded yet.</p>
            ) : (
              <div className="space-y-1.5 mt-3">
                {usage.heaviest_users_today.map((u) => (
                  <Row
                    key={u.user_id}
                    left={u.user_id === 'anon' ? 'anon (demo)' : `user ${u.user_id}`}
                    right={`${u.api_calls.toLocaleString()} calls`}
                    warn={usage.per_user_budget > 0 && u.api_calls >= usage.per_user_budget * 0.8}
                  />
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      <p className="inline-flex items-start gap-2 text-xs text-fg-mute leading-relaxed">
        <Wallet size={13} className="shrink-0 mt-0.5" />
        <span>
          Counts are recorded whether a fetch succeeded or failed, because a call that errored
          part-way still billed for what it managed.
        </span>
      </p>
    </div>
  );
}

function Figure({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'neutral' | 'bad';
}) {
  return (
    <div>
      <div className="meta meta-hi">{label}</div>
      <div
        className={`stat-value mt-1 text-xl ${tone === 'bad' ? 'text-tier-high' : 'text-fg'}`}
      >
        {value}
      </div>
    </div>
  );
}

function Row({ left, right, warn = false }: { left: string; right: string; warn?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="font-mono text-xs text-fg-dim truncate">{left}</span>
      <span className={`font-mono text-xs tabular-nums ${warn ? 'text-tier-high' : 'text-fg'}`}>
        {right}
      </span>
    </div>
  );
}
