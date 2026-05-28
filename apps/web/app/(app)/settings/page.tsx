import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { getCurrentUser } from '@/lib/auth';
import { ManageSubscriptionButton } from './manage-subscription-button';
import { NotificationsBlock } from './notifications-block';

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

      <NotificationsBlock />

      <Card>
        <CardLabel>Danger zone</CardLabel>
        <p className="text-sm text-fg-dim mb-4">
          Delete your account and all associated data. This cannot be undone.
        </p>
        <Button variant="danger" disabled title="Coming in Phase 2">
          Delete account
        </Button>
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
