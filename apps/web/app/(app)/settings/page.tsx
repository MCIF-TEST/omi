import Link from 'next/link';
import { Target, ArrowRight, Clock, Gauge } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { getCurrentUser } from '@/lib/auth';
import { ManageSubscriptionButton } from './manage-subscription-button';
import { NotificationsBlock } from './notifications-block';
import { ReferralBlock } from './referral-block';
import { DeleteAccountButton } from './delete-account-button';

export const metadata = { title: 'Settings — OMISPHERE' };

export default async function SettingsPage() {
  const user = await getCurrentUser();
  if (!user) return null;

  return (
    <div className="space-y-8 max-w-3xl">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Account
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">Settings</h1>
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
              user.subscription_status === 'active'
                ? <Badge variant="accent">Active</Badge>
                : user.subscription_status === 'canceled'
                  ? <Badge variant="warn">Canceled</Badge>
                  : <Badge variant="neutral">Free trial</Badge>
            }
          />
          <Row
            label="Renews"
            value={
              user.subscription_renews_at
                ? new Date(user.subscription_renews_at).toLocaleDateString()
                : '—'
            }
          />
        </dl>
      </Card>

      <Card>
        <CardLabel>Billing</CardLabel>
        <CardTitle>$9.99 / month · 20 scans</CardTitle>
        <p className="text-sm text-fg-dim mb-5">
          {user.subscription_status === 'active'
            ? 'Manage your subscription, update payment method, or cancel from Stripe.'
            : 'Subscribe to unlock 20 comprehensive scans per month.'}
        </p>
        <ManageSubscriptionButton active={user.subscription_status === 'active'} />
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
          className="flex items-center justify-between gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/40 transition-colors"
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
              href="/settings/engine"
              className="flex items-center justify-between gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/40 transition-colors"
            >
              <div className="flex items-center gap-3">
                <Gauge size={16} className="text-accent" />
                <div>
                  <div className="text-fg font-medium">Engine intelligence</div>
                  <div className="text-xs text-fg-dim mt-0.5">
                    Benchmark scoreboard — accuracy, coordination rescue, and the
                    memory learning curve.
                  </div>
                </div>
              </div>
              <ArrowRight size={14} className="text-fg-mute" />
            </Link>
            <Link
              href="/settings/calibration"
              className="flex items-center justify-between gap-3 p-3 rounded-sm border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/40 transition-colors"
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
