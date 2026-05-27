'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api';

export function ManageSubscriptionButton({ active }: { active: boolean }) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onClick = async () => {
    setError(null);
    setPending(true);
    try {
      const path = active ? '/v1/billing/portal' : '/v1/billing/create-checkout-session';
      const { url } = await apiClient<{ url: string }>(path, { method: 'POST' });
      window.location.href = url;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not start checkout.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button onClick={onClick} disabled={pending}>
        {pending ? 'Opening Stripe…' : active ? 'Manage subscription' : 'Subscribe — $9.99/mo'}
      </Button>
      {error && (
        <p className="text-xs text-danger font-mono">{error}</p>
      )}
    </div>
  );
}
