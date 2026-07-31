'use client';

import { useState } from 'react';
import { Flag, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ApiError, apiClient } from '@/lib/api';

/**
 * The recourse for someone named in this report.
 *
 * This page makes scored claims about real, identifiable accounts whose owners never agreed to be
 * analysed, and those claims get posted publicly. A person who thinks it is wrong about them needs a
 * way to say so that does not require creating an account with the product accusing them, which is
 * why the form is here rather than behind a signup, and why it asks for as little as possible.
 *
 * `no-print` like the other interactive blocks: a dispute form inside an exported PDF is noise.
 *
 * Filing does not take the report down. Saying so plainly is better than implying a takedown we do
 * not perform, and it is the honest description of what happens next.
 */
export function DisputeBlock({ token }: { token: string }) {
  const [open, setOpen] = useState(false);
  const [handle, setHandle] = useState('');
  const [contact, setContact] = useState('');
  const [reason, setReason] = useState('');
  const [pending, setPending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 10) {
      setError('Please say what is wrong with the report so we can check it.');
      return;
    }
    setError(null);
    setPending(true);
    try {
      await apiClient(`/r/${encodeURIComponent(token)}/dispute`, {
        method: 'POST',
        body: JSON.stringify({
          subject_handle: handle.trim() || null,
          contact: contact.trim() || null,
          reason: reason.trim(),
        }),
      });
      setDone(true);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : 'That could not be sent. Please try again in a moment.',
      );
      setPending(false);
    }
  };

  if (done) {
    return (
      <div className="no-print rounded-md border border-tier-low/40 bg-tier-low/[0.07] p-4 flex items-start gap-3">
        <Check size={16} className="text-tier-low mt-0.5 shrink-0" />
        <div>
          <p className="text-sm text-fg font-medium mb-1">Your objection has been recorded.</p>
          <p className="text-sm text-fg-dim leading-relaxed">
            A person will review this report against the evidence behind it. If you left a contact
            address we will tell you the outcome either way.
          </p>
        </div>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="no-print">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="inline-flex items-center gap-2 font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg transition-colors"
        >
          <Flag size={12} />
          Named in this report? Request a review
        </button>
      </div>
    );
  }

  return (
    <form
      onSubmit={submit}
      className="no-print rounded-md border border-border-1 bg-bg-elev p-5 space-y-4"
    >
      <div>
        <p className="display text-base font-semibold text-fg tracking-tight mb-1.5">
          Request a review of this report
        </p>
        <p className="text-sm text-fg-dim leading-relaxed">
          Every score here is probabilistic and can be wrong. Tell us what this report gets wrong
          about the account and a person will check it against the evidence it was based on.
          Submitting this does not remove the report on its own.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
            Account named
          </span>
          <input
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            placeholder="@handle"
            className="mt-1 h-10 w-full px-3 text-base rounded-md bg-bg-inset border border-border-2 text-fg placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
          />
        </label>
        <label className="block">
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
            Contact (optional)
          </span>
          <input
            value={contact}
            onChange={(e) => setContact(e.target.value)}
            placeholder="you@example.com"
            inputMode="email"
            autoCapitalize="off"
            autoCorrect="off"
            className="mt-1 h-10 w-full px-3 text-base rounded-md bg-bg-inset border border-border-2 text-fg placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
          />
        </label>
      </div>

      <label className="block">
        <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
          What is wrong with it
        </span>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          required
          placeholder="For example: the posts this describes are not from my account, or the account is a business rather than an automated one."
          className="mt-1 w-full px-3 py-2 text-base rounded-md bg-bg-inset border border-border-2 text-fg placeholder:text-fg-faint leading-relaxed focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
        />
      </label>

      {error && (
        <p className="text-sm text-danger" role="alert">
          {error}
        </p>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? <Loader2 size={14} className="animate-spin" /> : <Flag size={14} />}
          {pending ? 'Sending…' : 'Send for review'}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
