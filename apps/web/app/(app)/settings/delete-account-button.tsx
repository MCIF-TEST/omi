'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiClient, ApiError } from '@/lib/api';

export function DeleteAccountButton({ email }: { email: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const matches = confirm.trim().toLowerCase() === email.toLowerCase();

  const onDelete = async () => {
    if (!matches) return;
    setPending(true);
    setError(null);
    try {
      await apiClient('/v1/auth/account', {
        method: 'DELETE',
        body: JSON.stringify({ confirm_email: confirm.trim() }),
      });
      // Account + session are gone — send them to the landing page.
      router.refresh();
      router.push('/');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete account. Try again.');
      setPending(false);
    }
  };

  if (!open) {
    return (
      <Button variant="danger" onClick={() => setOpen(true)}>
        Delete account
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-sm border border-danger/40 bg-danger/[0.06] p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="text-danger shrink-0 mt-0.5" />
        <p className="text-sm text-fg leading-relaxed">
          This permanently deletes your account, scan logs, saved
          investigations, watchlists, and graphs. This cannot be undone. Type{' '}
          <span className="font-mono text-fg-dim">{email}</span> to confirm.
        </p>
      </div>
      <Input
        type="email"
        autoComplete="off"
        placeholder="Retype your email"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
      />
      {error && (
        <p className="text-xs text-danger font-mono">{error}</p>
      )}
      <div className="flex items-center gap-2">
        <Button variant="danger" disabled={!matches || pending} onClick={onDelete}>
          {pending ? 'Deleting…' : 'Permanently delete'}
        </Button>
        <Button
          variant="ghost"
          disabled={pending}
          onClick={() => { setOpen(false); setConfirm(''); setError(null); }}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
