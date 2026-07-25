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

/** What POST /v1/billing/sync returns after reconciling against Stripe. */
interface SyncResponse {
  synced: boolean;
  granted: number;
  credits_added: number;
  credits_remaining: number;
  subscription_status: string | null;
}

const PAID = ['active', 'trialing'];

/**
 * Subscribe / manage button + the return-from-Stripe handshake.
 *
 * There is no webhook. When Stripe sends the customer back here, we ask our API to reconcile
 * against Stripe (`POST /v1/billing/sync`), which reads what was actually paid and grants the
 * credits. That call is what completes the purchase, so it retries for a few seconds: Checkout
 * occasionally redirects a beat before the invoice is marked paid, and a paying customer must never
 * be left looking at a "Subscribe" button and their old balance.
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

  // Drive the reconciliation until Stripe reports the subscription live. Bounded, so a payment that
  // never lands stops spinning and says so instead of pretending forever.
  useEffect(() => {
    if (!settling) return;
    let tries = 0;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (cancelled) return;
      tries += 1;
      try {
        const s = await apiClient<SyncResponse>('/v1/billing/sync', { method: 'POST' });
        setStatus((prev) => ({
          ...prev,
          credits_remaining: s.credits_remaining,
          subscription_status: s.subscription_status,
        }));
        if (PAID.includes(s.subscription_status ?? '')) {
          setSettling(false);
          router.refresh();
          return;
        }
      } catch {
        /* keep trying — a transient error here shouldn't end the handshake */
      }
      if (cancelled) return;
      if (tries >= 10) { setSettling(false); return; }
      timer = setTimeout(() => { void tick(); }, 2000);
    };
    timer = setTimeout(() => { void tick(); }, 1200);
    return () => { cancelled = true; clearTimeout(timer); };
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
