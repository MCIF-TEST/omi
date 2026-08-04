import { Suspense } from 'react';
import Link from 'next/link';
import { Target, ArrowRight, Clock, Gauge, MessageSquarePlus, Wallet } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { getCurrentUser } from '@/lib/auth';
import { PLAN_NAME } from '@/lib/plan';
import { apiServer } from '@/lib/api-server';
import { ManageSubscriptionButton, type BillingStatus } from './manage-subscription-button';
import { NotificationsBlock } from './notifications-block';
import { ReferralBlock } from './referral-block';
import { DeleteAccountButton } from './delete-account-button';

export const metadata = { title: 'Settings. OMISPHERE' };

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  // Fails soft: if the API is unreachable the page still renders, with billing reported as not
  // configured rather than showing a Subscribe button that would 503 on click.
  const billing = await apiServer<BillingStatus>('/v1/billing/status').catch((): BillingStatus => ({
    configured: false,
    credits_remaining: user.credits_remaining,
    subscription_status: user.subscription_status ?? null,
    subscription_renews_at: null,
    price_display: '$13.99',
    credits_per_period: 20,
  }));

  return (
    <div className="space-y-8 max-w-3xl">
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <span className="section-label">Operations · Account</span>
        <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-3">Settings</h1>
      </header>

      <Card>
        <CardLabel>Account</CardLabel>
        <CardTitle>{user.email}</CardTitle>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
          <Row label="User ID" value={`#${user.id}`} />
          <Row label="Credits remaining" value={String(user.credits_remaining)} />
          <Row
            label="Subscription"
            value={
              // An active subscriber IS an Omi Premium Member, so name the membership rather than
              // repeating the word "active". The other two states stay statuses, because neither one
              // is a membership.
              user.subscription_status === 'active'
                ? <span className="font-mono text-2xs tracking-wider uppercase text-accent-text">{PLAN_NAME}</span>
                : user.subscription_status === 'canceled'
                  ? <span className="font-mono text-2xs tracking-wider uppercase text-warn">Canceled</span>
                  : <span className="font-mono text-2xs tracking-wider uppercase text-fg-dim">Free trial</span>
            }
          />
          <Row
            label="Renews"
            value={
              user.subscription_renews_at
                ? new Date(user.subscription_renews_at).toLocaleDateString()
                : '-'
            }
          />
        </dl>
      </Card>

      <Card>
        <CardLabel>Billing</CardLabel>
        {/* Figures come from the API, which reads them from the same settings that drive the actual
            charge and grant, so this card cannot drift from what a customer is really billed. */}
        <CardTitle>{PLAN_NAME}</CardTitle>
        <p className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-3">
          {billing.price_display} / month · {billing.credits_per_period} credits
        </p>
        <p className="text-sm text-fg-dim mb-5">
          {billing.subscription_status === 'active' || billing.subscription_status === 'trialing'
            ? `${billing.credits_per_period} credits are added each month. Update your card or cancel any time from Stripe.`
            : `${billing.credits_per_period} credits a month, one credit covers up to 50 accounts, so that is up to ${(billing.credits_per_period * 50).toLocaleString()} accounts analysed.`}
        </p>
        <Suspense fallback={null}>
          <ManageSubscriptionButton initial={billing} isAdmin={user.is_admin} />
        </Suspense>
      </Card>

      <ReferralBlock
        referralCode={user.referral_code}
        creditsEarned={user.referral_credits_earned}
      />

      <NotificationsBlock />

      <Card>
        <CardLabel>History</CardLabel>
        <Link
          href="/settings/activity"
          className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-border-1 card-interactive"
        >
          <div className="flex items-center gap-3">
            <Clock size={16} className="text-fg-dim" />
            <div>
              <div className="text-fg font-medium">Activity log</div>
              <div className="text-xs text-fg-dim mt-0.5">
                Every scan you&apos;ve run · credit usage · refunds
              </div>
            </div>
          </div>
          <ArrowRight size={14} className="text-fg-mute" />
        </Link>
      </Card>

      {user.is_admin && (
        <Card>
          <CardLabel>Admin</CardLabel>
          <div className="space-y-2">
            <Link
              href="/settings/feedback"
              className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-border-1 card-interactive"
            >
              <div className="flex items-center gap-3">
                <MessageSquarePlus size={16} className="text-accent" />
                <div>
                  <div className="text-fg font-medium">Feedback queue</div>
                  <div className="text-xs text-fg-dim mt-0.5">
                    Everything users have sent. Searchable by keyword or email.
                  </div>
                </div>
              </div>
              <ArrowRight size={14} className="text-fg-mute" />
            </Link>
            <Link
              href="/settings/engine"
              className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-border-1 card-interactive"
            >
              <div className="flex items-center gap-3">
                <Gauge size={16} className="text-accent" />
                <div>
                  <div className="text-fg font-medium">Engine intelligence</div>
                  <div className="text-xs text-fg-dim mt-0.5">
                    Benchmark scoreboard. Accuracy, coordination rescue, and the
                    memory learning curve.
                  </div>
                </div>
              </div>
              <ArrowRight size={14} className="text-fg-mute" />
            </Link>
            <Link
              href="/settings/spend"
              className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-border-1 card-interactive"
            >
              <div className="flex items-center gap-3">
                <Wallet size={16} className="text-accent" />
                <div>
                  <div className="text-fg font-medium">Upstream spend</div>
                  <div className="text-xs text-fg-dim mt-0.5">
                    What today&apos;s scanning cost against the daily ceilings, and who spent it.
                  </div>
                </div>
              </div>
              <ArrowRight size={14} className="text-fg-mute" />
            </Link>
            <Link
              href="/settings/calibration"
              className="flex items-center justify-between gap-3 p-3.5 rounded-xl border border-border-1 card-interactive"
            >
              <div className="flex items-center gap-3">
                <Target size={16} className="text-accent" />
                <div>
                  <div className="text-fg font-medium">Calibration</div>
                  <div className="text-xs text-fg-dim mt-0.5">
                    Live engine accuracy against your labeled corpus.
                  </div>
                </div>
              </div>
              <ArrowRight size={14} className="text-fg-mute" />
            </Link>
          </div>
        </Card>
      )}

      <Card>
        <CardLabel>Danger zone</CardLabel>
        <p className="text-sm text-fg-dim mb-4">
          Delete your account and all associated data. This cannot be undone.
        </p>
        <DeleteAccountButton email={user.email} />
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">
        {label}
      </dt>
      <dd className="text-fg">{value}</dd>
    </div>
  );
}
