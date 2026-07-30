'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api';
import { PLAN_NAME } from '@/lib/plan';

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
 * Credits normally arrive by webhook before the browser gets back here. This handshake is the
 * backstop: on return from Checkout we POST /v1/billing/sync (with the Checkout session_id when
 * present) so the server asks Stripe what was paid and grants anything the webhook didn't. Both
 * paths claim the same per-invoice row, so this can never double-credit.
 */
export function ManageSubscriptionButton({
  initial,
  isAdmin = false,
}: {
  initial: BillingStatus;
  isAdmin?: boolean;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const justPaid = params?.get('billing') === 'success';
  const canceled = params?.get('billing') === 'cancel';
  const checkoutSessionId = params?.get('session_id') || null;

  const [status, setStatus] = useState<BillingStatus>(initial);
  const [pending, setPending] = useState(false);
  const [settling, setSettling] = useState(
    justPaid && !PAID.includes(initial.subscription_status ?? ''),
  );
  const [error, setError] = useState<string | null>(null);

  const active = PAID.includes(status.subscription_status ?? '');
  const pastDue = status.subscription_status === 'past_due';

  useEffect(() => {
    if (!settling) return;
    let tries = 0;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (cancelled) return;
      tries += 1;
      try {
        const qs = checkoutSessionId
          ? `?session_id=${encodeURIComponent(checkoutSessionId)}`
          : '';
        const s = await apiClient<SyncResponse>(`/v1/billing/sync${qs}`, {
          method: 'POST',
          body: '{}',
        });
        setStatus((prev) => ({
          ...prev,
          credits_remaining: s.credits_remaining,
          subscription_status: s.subscription_status,
        }));
        if (PAID.includes(s.subscription_status ?? '') || s.granted > 0) {
          setSettling(false);
          router.refresh();
          return;
        }
      } catch {
        /* keep trying. Stripe can lag a beat after redirect */
      }
      if (cancelled) return;
      // ~45s of retries: live mode invoice visibility is usually fast but not instant.
      if (tries >= 15) {
        setSettling(false);
        return;
      }
      timer = setTimeout(() => {
        void tick();
      }, 2500);
    };
    timer = setTimeout(() => {
      void tick();
    }, 800);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [settling, router, checkoutSessionId]);

  const onClick = async () => {
    setError(null);
    setPending(true);
    try {
      const path =
        active || pastDue ? '/v1/billing/portal' : '/v1/billing/create-checkout-session';
      const { url } = await apiClient<{ url: string }>(path, {
        method: 'POST',
        body: '{}',
      });
      if (!url || typeof url !== 'string' || !url.startsWith('https://')) {
        setError(
          isAdmin
            ? 'Stripe returned no checkout URL. Confirm OMI_STRIPE_SECRET_KEY, OMI_STRIPE_PRICE_ID (price_…), and OMI_PUBLIC_BASE_URL on the API service.'
            : 'Checkout could not be opened. Nothing has been charged. Please try again shortly.',
        );
        setPending(false);
        return;
      }
      window.location.href = url;
    } catch (e) {
      let message = 'Could not start checkout.';
      if (e instanceof ApiError) {
        message = e.message || message;
        if (e.status === 401) {
          message = 'You need to sign in again before subscribing.';
        } else if (e.status === 503) {
          // The 503 body already explains the misconfiguration; only an admin can act on the
          // env-var detail, and only an admin should be reading it.
          message = isAdmin
            ? `${message} Check API env: OMI_STRIPE_SECRET_KEY (sk_…), OMI_STRIPE_PRICE_ID (price_…, not a dollar amount), OMI_PUBLIC_BASE_URL (web https URL).`
            : 'Subscriptions are temporarily unavailable. Nothing has been charged.';
        }
      }
      setError(message);
      setPending(false);
    }
  };

  if (!status.configured) {
    // Two audiences, two messages. A customer gets a plain apology; only an admin sees the env-var
    // names, because the old text showed every user OMI_STRIPE_SECRET_KEY and read as though card
    // payments were a product limitation rather than a server that has not been configured.
    return isAdmin ? (
      <p className="text-sm text-fg-mute">
        Billing is not configured on this deployment. On the API service set{' '}
        <span className="font-mono text-2xs">OMI_STRIPE_SECRET_KEY</span> (sk_…) and{' '}
        <span className="font-mono text-2xs">OMI_STRIPE_PRICE_ID</span> (a price_… id, not a dollar
        amount), plus <span className="font-mono text-2xs">OMI_PUBLIC_BASE_URL</span> (your web
        https URL), then redeploy. Call{' '}
        <span className="font-mono text-2xs">/v1/billing/preflight</span> on the API host to see
        which one is missing.
      </p>
    ) : (
      <p className="text-sm text-fg-mute">
        Subscriptions are not available just yet. Your existing credits still work, and nothing has
        been charged. Please check back shortly.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {justPaid && (
        <p className="text-sm text-tier-low" role="status">
          {settling
            ? 'Payment received. Adding your credits…'
            : active
              ? `Payment received. ${status.credits_remaining} credits are on your account.`
              : 'Payment received. If credits are not visible yet, open this page again in a moment.'}
        </p>
      )}
      {canceled && (
        <p className="text-sm text-fg-mute" role="status">
          Checkout cancelled. You haven&apos;t been charged.
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
              : `Become an ${PLAN_NAME} · ${status.price_display}/mo`}
      </Button>

      {error && (
        <p className="text-xs text-danger font-mono whitespace-pre-wrap break-words" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
