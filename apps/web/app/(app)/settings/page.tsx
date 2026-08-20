import { Suspense } from 'react';
import Link from 'next/link';
import { Target, ArrowRight, Clock, Gauge, MessageSquarePlus, Wallet } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { getCurrentUser } from '@/lib/auth';
import {
  ACCOUNTS_PER_CREDIT, FREE_TIER, PLAN_NAME, PLAN_TIERS, TOPUP_CREDITS, TOPUP_PRICE,
} from '@/lib/plan';
import { apiServer } from '@/lib/api-server';
import { ManageSubscriptionButton, type BillingStatus } from './manage-subscription-button';
import { NotificationsBlock } from './notifications-block';
import { ReferralBlock } from './referral-block';
import { DeleteAccountButton } from './delete-account-button';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

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
    // Derived from the catalog, never written out: a hardcoded fallback price is a number that
    // silently goes stale and then advertises the wrong figure on the one page about money.
    price_display: PLAN_TIERS[0].price,
    credits_per_period: PLAN_TIERS[0].credits,
    plan_tier: 'free',
    plan_name: FREE_TIER.name,
    plan_features: [],
    calls_used: 0,
    calls_included: 0,
    topup_credits: TOPUP_CREDITS,
    topup_price_display: TOPUP_PRICE,
  }));

  const isSubscribed =
    billing.subscription_status === 'active' || billing.subscription_status === 'trialing';

  return (
    <div className="space-y-8 max-w-3xl">
      <ConsoleHeader
        index={SECTION_INDEX['/settings']}
        eyebrow="Operations · Account"
        title="Settings"
      />

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
        {/* The plan NAME comes from the server, which resolved it from the Stripe Price on the
            invoice the customer actually paid. Reading a single global plan name here was right
            with one plan and would now show a Research subscriber the entry tier. */}
        <CardTitle>{billing.plan_name || PLAN_NAME}</CardTitle>
        <p className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-3">
          {billing.price_display} / month · {billing.credits_per_period} credits
        </p>
        <p className="text-sm text-fg-dim mb-5">
          {isSubscribed
            ? `${billing.credits_per_period} credits are added each month, covering up to ${(billing.credits_per_period * ACCOUNTS_PER_CREDIT).toLocaleString()} accounts. Update your card, change plan or cancel any time from Stripe.`
            : `One credit covers ${ACCOUNTS_PER_CREDIT} accounts. Choose a plan to get monthly credits.`}
        </p>

        {/* The lookup meter. Loading a comment section calls the platform whether or not anyone is
            scanned, so this ceiling is what lets the plan be priced. The customer should meet it
            here, with room to act, rather than at a refusal in the middle of an investigation. */}
        {billing.calls_included > 0 && (
          <div className="border-t border-border-1 pt-3 mb-5">
            <div className="flex items-baseline justify-between gap-3 mb-1.5">
              <span className="meta">Lookups this month</span>
              <span className="font-mono text-xs text-fg tabular-nums">
                {billing.calls_used.toLocaleString()} / {billing.calls_included.toLocaleString()}
              </span>
            </div>
            <div className="h-1 bg-bg-elev overflow-hidden" role="presentation">
              <div
                className="h-full bg-border-hot"
                style={{
                  width: `${Math.min(100, (billing.calls_used / billing.calls_included) * 100)}%`,
                }}
              />
            </div>
          </div>
        )}
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
      <dt className="meta meta-hi mb-0.5">{label}</dt>
      <dd className="text-fg">{value}</dd>
    </div>
  );
}
