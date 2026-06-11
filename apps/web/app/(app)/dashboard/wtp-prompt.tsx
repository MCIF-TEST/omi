'use client';

import { useState } from 'react';
import { MessageCircleQuestion, X } from 'lucide-react';
import { apiClient } from '@/lib/api';

/**
 * The single willingness-to-pay question (founder-learning Q5). Server-gated:
 * only rendered for returners (>=2 investigations) who have neither answered
 * nor dismissed it — so this asks exactly once, ever, of exactly the users
 * whose answer means something.
 */
export function WtpPrompt() {
  const [text, setText] = useState('');
  const [state, setState] = useState<'open' | 'sent' | 'gone'>('open');

  if (state === 'gone') return null;
  if (state === 'sent') {
    return (
      <div className="border border-tier-low/30 bg-tier-low/[0.06] rounded-lg px-4 py-3 text-sm text-fg-dim">
        Thank you — this goes straight to the founder.
      </div>
    );
  }

  const submit = async () => {
    const answer = text.trim();
    if (!answer) return;
    try {
      await apiClient('/v1/learning/wtp', {
        method: 'POST',
        body: JSON.stringify({ text: answer }),
      });
      setState('sent');
    } catch {
      setState('gone'); // never nag on failure
    }
  };

  const dismiss = async () => {
    setState('gone');
    try {
      await apiClient('/v1/learning/wtp/dismiss', { method: 'POST' });
    } catch { /* best-effort */ }
  };

  return (
    <div className="border border-accent/25 bg-accent/[0.04] rounded-lg p-4">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2">
          <MessageCircleQuestion size={15} className="text-accent shrink-0" />
          <p className="text-sm font-medium text-fg">
            One question — what would make Omi worth paying for?
          </p>
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss permanently"
          className="text-fg-mute hover:text-fg shrink-0"
        >
          <X size={14} />
        </button>
      </div>
      <p className="text-xs text-fg-dim mb-3">
        You&apos;ve run a few investigations, so your answer carries weight. One
        sentence is plenty; asked once, read by a human.
      </p>
      <div className="flex gap-2">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void submit(); }}
          maxLength={2000}
          placeholder="e.g. court-ready PDF exports, alerts when a campaign recurs…"
          className="flex-1 h-9 px-3 bg-bg border border-border-2 rounded-sm text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!text.trim()}
          className="px-4 h-9 bg-accent text-bg-deep text-sm font-semibold rounded-sm hover:bg-accent-2 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}
