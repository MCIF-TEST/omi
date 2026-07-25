'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api';

export interface BillingStatus {
  configured: boolean;
  credits_remaining: number;
  subscription_status: string | null;
  subscription_renews_at: string | null;
  price_display: string;
  credits_per_period: number;
}

const PAID = ['active', 'trialing'];

/**
 * Subscribe / manage button + the return-from-Stripe handshake.
 *
 * Stripe redirects the browser back the moment payment succeeds, but the credits arrive on a
 * WEBHOOK, which lands a beat later and out of band. Without this, a paying customer returns to a
 * page that still says "Subscribe" with their old balance — the most alarming possible moment to
 * look broken. So on `?billing=success` we poll our own status until the subscription flips, then
 * refresh the server components.
 */
export function ManageSubscriptionButton({ initial }: { initial: BillingStatus }) {
  const router = useRouter();
  const params = useSearchParams();
  const justPaid = params?.get('billing') === 'success';
  const canceled = params?.get('billing') === 'cancel';

  const [status, setStatus] = useState<BillingStatus>(initial);
  const [pending, setPending] = useState(false);
  const [settling, setSettling] = useState(justPaid && !PAID.includes(initial.subscription_status ?? ''));
  const [error, setError] = useState<string | null>(null);

  const active = PAID.includes(status.subscription_status ?? '');
  const pastDue = status.subscription_status === 'past_due';

  // Poll for the webhook to land — bounded, so a webhook that never arrives stops spinning and says
  // so rather than pretending forever.
  useEffect(() => {
    if (!settling) return;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      tries += 1;
      try {
        const s = await apiClient<BillingStatus>('/v1/billing/status');
        setStatus(s);
        if (PAID.includes(s.subscription_status ?? '')) {
          setSettling(false);
          router.refresh();
          return;
        }
      } catch {
        /* keep trying — a transient error here shouldn't end the handshake */
      }
      if (tries >= 15) { setSettling(false); return; }
      timer = setTimeout(() => { void tick(); }, 2000);
    };
    timer = setTimeout(() => { void tick(); }, 1500);
    return () => clearTimeout(timer);
  }, [settling, router]);

  const onClick = async () => {
    setError(null);
    setPending(true);
    try {
      const path = active || pastDue ? '/v1/billing/portal' : '/v1/billing/create-checkout-session';
      const { url } = await apiClient<{ url: string }>(path, { method: 'POST' });
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start checkout.');
      setPending(false);
    }
  };

  if (!status.configured) {
    return (
      <p className="text-sm text-fg-mute">
        Card payments aren&apos;t switched on for this deployment yet.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {justPaid && (
        <p className="text-sm text-tier-low" role="status">
          {settling
            ? 'Payment received — adding your credits…'
            : active
              ? `Payment received. ${status.credits_remaining} credits are on your account.`
              : 'Payment received. Your credits will appear shortly — reload if they don’t.'}
        </p>
      )}
      {canceled && (
        <p className="text-sm text-fg-mute" role="status">
          Checkout cancelled — you haven&apos;t been charged.
        </p>
      )}
      {pastDue && (
        <p className="text-sm text-warn">
          Your last payment didn&apos;t go through. Update your card to keep your subscription.
        </p>
      )}

      <Button onClick={onClick} disabled={pending || settling}>
        {pending
          ? 'Opening Stripe…'
          : pastDue
            ? 'Update payment method'
            : active
              ? 'Manage subscription'
              : `Subscribe — ${status.price_display}/mo`}
      </Button>

      {error && <p className="text-xs text-danger font-mono">{error}</p>}
    </div>
  );
}
