'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { MessageSquarePlus, X, Loader2, Check } from 'lucide-react';
import { submitFeedback, ApiError } from '@/lib/api';

const CATEGORIES = [
  { value: 'idea', label: 'Idea' },
  { value: 'bug', label: 'Bug' },
  { value: 'praise', label: 'Praise' },
  { value: 'general', label: 'General' },
] as const;

/**
 * Persistent feedback control, a subtle button that lives in the header on every page (including
 * deep inside an investigation). Opens a lightweight modal: a category, a message, submit. Sends to
 * the admin-only feedback queue. Fails soft, never blocks the user.
 */
export function FeedbackButton() {
  const pathname = usePathname() || '';
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<string>('idea');
  const [message, setMessage] = useState('');
  const [state, setState] = useState<'idle' | 'sending' | 'done' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    // reset after the close animation
    setTimeout(() => { setState('idle'); setMessage(''); setError(null); setCategory('idea'); }, 200);
  };

  const send = async () => {
    if (!message.trim() || state === 'sending') return;
    setState('sending');
    setError(null);
    try {
      await submitFeedback({ message: message.trim(), category, page: pathname });
      setState('done');
      setTimeout(close, 1100);
    } catch (e) {
      setState('error');
      setError(e instanceof ApiError ? e.message : 'Could not send feedback. Please try again.');
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="tap inline-flex items-center gap-1.5 h-8 px-2.5 rounded-md text-fg-mute hover:text-fg
                   hover:bg-bg-elev-2 transition-colors text-xs font-medium"
        aria-label="Send feedback"
        title="Send feedback"
      >
        <MessageSquarePlus size={15} />
        <span className="hidden sm:inline">Feedback</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[100] flex items-end sm:items-center justify-center p-0 sm:p-4" role="dialog" aria-modal="true" aria-label="Send feedback">
          <div className="fb-scrim absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={close} />
          <div className="fb-panel relative w-full sm:max-w-md bg-bg-elev border border-border-1 rounded-t-2xl sm:rounded-2xl shadow-overlay safe-bottom">
            <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-divider">
              <h2 className="text-sm font-semibold text-fg inline-flex items-center gap-2">
                <MessageSquarePlus size={16} className="text-accent" /> Send feedback
              </h2>
              <button type="button" onClick={close} aria-label="Close" className="tap text-fg-mute hover:text-fg p-1 -mr-1">
                <X size={18} />
              </button>
            </div>

            {state === 'done' ? (
              <div className="px-5 py-10 text-center">
                <span className="mx-auto mb-3 grid place-items-center w-11 h-11 rounded-full bg-tier-low/15 text-tier-low">
                  <Check size={22} />
                </span>
                <p className="text-sm text-fg font-medium">Thanks. Got it.</p>
                <p className="text-xs text-fg-mute mt-1">Your feedback went straight to the team.</p>
              </div>
            ) : (
              <div className="px-5 py-4 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((c) => (
                    <button
                      key={c.value}
                      type="button"
                      onClick={() => setCategory(c.value)}
                      className={`h-8 px-3 rounded-full text-xs font-medium border transition-colors ${
                        category === c.value
                          ? 'border-accent bg-accent/10 text-accent-text'
                          : 'border-border-2 text-fg-mute hover:text-fg-dim'
                      }`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="What's on your mind? Bugs, ideas, anything…"
                  rows={5}
                  autoFocus
                  className="w-full rounded-lg bg-bg-inset border border-border-2 text-fg text-sm p-3 leading-relaxed
                             placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline resize-none"
                />
                {error && <p className="text-xs text-danger">{error}</p>}
                <div className="flex items-center justify-end gap-2 pt-1">
                  <button type="button" onClick={close} className="btn-slab h-9 px-4 rounded-md text-sm text-fg-dim">Cancel</button>
                  <button
                    type="button"
                    onClick={send}
                    disabled={!message.trim() || state === 'sending'}
                    className="btn-lamp h-9 px-5 rounded-md text-sm font-semibold inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {state === 'sending' ? <><Loader2 size={14} className="animate-spin" /> Sending…</> : 'Send feedback'}
                  </button>
                </div>
              </div>
            )}
          </div>
          <style jsx>{`
            .fb-scrim { animation: fb-fade 160ms ease-out; }
            .fb-panel { animation: fb-in 220ms cubic-bezier(0.23, 1, 0.32, 1); }
            @keyframes fb-fade { from { opacity: 0; } to { opacity: 1; } }
            @keyframes fb-in { from { opacity: 0; transform: translateY(12px) scale(0.98); } to { opacity: 1; transform: none; } }
            @media (prefers-reduced-motion: reduce) { .fb-scrim, .fb-panel { animation: none; } }
          `}</style>
        </div>
      )}
    </>
  );
}
