'use client';

import { useState, type FormEvent } from 'react';
import { MailCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input, Label } from '@/components/ui/input';
import { apiClient, ApiError } from '@/lib/api';

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await apiClient('/v1/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email }),
      });
      // The API always returns a generic success (anti-enumeration), so we
      // show the same confirmation regardless of whether the email exists.
      setSent(true);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.status === 429
            ? 'Too many requests. Please wait a few minutes and try again.'
            : e.message
          : 'Something went wrong. Try again.',
      );
    } finally {
      setPending(false);
    }
  };

  if (sent) {
    return (
      <div className="rounded-sm border border-accent/40 bg-accent/[0.06] p-4 flex items-start gap-3">
        <MailCheck size={18} className="text-accent shrink-0 mt-0.5" />
        <div>
          <p className="text-sm text-fg font-medium mb-1">Check your inbox</p>
          <p className="text-xs text-fg-dim leading-relaxed">
            If an account exists for <span className="text-fg font-mono">{email}</span>, a
            reset link is on its way. The link expires in 60 minutes.
          </p>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" autoComplete="on">
      <div>
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>
      {error && (
        <p className="text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" className="w-full" disabled={pending}>
        {pending ? 'Sending…' : 'Send reset link'}
      </Button>
    </form>
  );
}
