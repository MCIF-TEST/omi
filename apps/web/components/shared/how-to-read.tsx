'use client';

import { useEffect, useState } from 'react';
import { BookOpen, X } from 'lucide-react';

/**
 * "How to read this", a dismissible first-view comprehension aid on the
 * campaign report surfaces. Phase 3 made the value moment visible; this turns
 * "saw a campaign" into "understood why it's trustworthy" by naming the
 * reading order (corroboration → evidence for/against → recurrence).
 *
 * Client-only and self-gating via localStorage so it appears once and never
 * nags, no backend, no new system. ``storageKey`` lets the campaign-detail
 * and public-report instances dismiss independently.
 */
export function HowToRead({ storageKey }: { storageKey: string }) {
  const key = `omi.howtoread.${storageKey}`;
  // Start hidden; reveal after mount only if not previously dismissed, so SSR
  // and the no-localStorage case never flash the banner.
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(key) !== 'dismissed') setShow(true);
    } catch { setShow(true); }
  }, [key]);

  if (!show) return null;

  const dismiss = () => {
    setShow(false);
    try { localStorage.setItem(key, 'dismissed'); } catch { /* best-effort */ }
  };

  return (
    <aside className="no-print border border-border-2 bg-bg-elev/40 rounded-md p-4 text-sm">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 font-mono text-2xs uppercase tracking-wider text-fg-mute">
          <BookOpen size={13} className="text-accent" />
          How to read this report
        </div>
        <button
          type="button"
          onClick={dismiss}
          aria-label="Dismiss"
          className="text-fg-mute hover:text-fg shrink-0"
        >
          <X size={14} />
        </button>
      </div>
      <ol className="space-y-1.5 text-fg-dim leading-relaxed list-decimal list-inside">
        <li>
          <span className="text-fg">Corroboration first.</span> A maximal verdict
          needs a discriminative detector (fingerprint, co-engagement, co-tag) or
          two independent methods agreeing. A{' '}
          <span className="text-tier-moderate">supporting-only</span> campaign is
          capped at MODERATE. Omi will not overclaim.
        </li>
        <li>
          <span className="text-fg">Evidence for and against, together.</span>{' '}
          Read both columns: what fired, and which detectors stayed silent or
          weakened the case. The verdict is a probability with its uncertainty,
          never a definitive judgement.
        </li>
        <li>
          <span className="text-fg">Recurrence over time.</span> The timeline
          shows whether this group keeps acting together, a campaign that
          returns is stronger evidence than a one-off cluster.
        </li>
      </ol>
    </aside>
  );
}
