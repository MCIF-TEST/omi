'use client';

import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';

/**
 * The one thing a visitor can do before launch.
 *
 * A pre-launch campaign drives somebody here ONCE. So this fails soft in every direction it can: a
 * duplicate submission is a success (being told "you are already on the list" as an error reads as
 * rejection at the exact moment you want somebody to feel welcomed), and a server error still tells
 * them what to do next rather than dead-ending.
 *
 * No third-party script. The privacy policy says this site loads no third-party analytics or
 * embeds, and a marketing form is not a good enough reason to make that untrue.
 */
export function WaitlistForm({
  source = 'coming_soon',
  cta = 'Join the waitlist',
  compact = false,
}: {
  source?: string;
  cta?: string;
  compact?: boolean;
}) {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (state === 'sending' || state === 'done') return;
    setState('sending');
    setError(null);
    try {
      await apiClient('/v1/waitlist', {
        method: 'POST',
        body: JSON.stringify({ email: email.trim(), source }),
      });
      setState('done');
    } catch (err) {
      setState('error');
      setError(
        err instanceof ApiError && err.status === 400
          ? 'That does not look like an email address.'
          : 'Could not reach the server. Please try again in a moment.',
      );
    }
  };

  if (state === 'done') {
    return (
      <p className="text-sm text-tier-low leading-relaxed" role="status">
        You are on the list. We will email you the moment OmiSphere opens.
      </p>
    );
  }

  return (
    <form onSubmit={submit} className={compact ? 'space-y-2' : 'space-y-3'} noValidate>
      <div className="flex flex-col sm:flex-row gap-2">
        <label htmlFor={`waitlist-${source}`} className="sr-only">
          Email address
        </label>
        <input
          id={`waitlist-${source}`}
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className="flex-1 min-w-0 h-11 px-3.5 bg-bg-deep border border-border-1 text-fg
                     placeholder:text-fg-faint font-mono text-sm rounded-[3px]
                     focus-hard focus-visible:outline-none"
        />
        <button
          type="submit"
          disabled={state === 'sending'}
          className="btn-lamp inline-flex items-center justify-center gap-2 h-11 px-5 shrink-0
                     text-[0.9375rem] font-semibold disabled:opacity-60
                     focus-hard focus-visible:outline-none"
        >
          {state === 'sending' ? 'Adding you…' : cta}
          {state !== 'sending' && <ArrowRight size={15} />}
        </button>
      </div>
      {error && (
        <p className="font-mono text-2xs text-danger" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
