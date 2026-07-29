'use client';

import { useState } from 'react';
import { cn } from '@/lib/cn';
import { ACCOUNT_SIGNAL_META, type AccountSignal, type Tier } from '@/lib/api';

// Score (0-100, higher = stronger bought/inauthentic tell) to the tier palette, matching the
// convention every other score bar on the site uses.
function signalTier(score: number): Tier {
  if (score >= 75) return 'high';
  if (score >= 50) return 'elevated';
  if (score >= 25) return 'moderate';
  return 'low';
}

const FILL: Record<Tier, string> = {
  low: 'bg-tier-low',
  moderate: 'bg-tier-moderate',
  elevated: 'bg-tier-elevated',
  high: 'bg-tier-high',
};
const TEXT: Record<Tier, string> = {
  low: 'text-tier-low',
  moderate: 'text-tier-moderate',
  elevated: 'text-tier-elevated',
  high: 'text-tier-high',
};

/**
 * One of the eight dimensions behind an account's OMI score.
 *
 * A null score renders as "n/a" over an empty track, never as 0. Null means the evidence this
 * dimension needs was never collected (rhythm cannot be read off an account with no posting
 * history), and drawing it as a zero-length low-tier bar would read as "this dimension looks
 * clean", which is a claim we did not make. Clicking the row reveals the model's sentence plus
 * what the dimension actually measures.
 *
 * No open/close animation on purpose: these rows are cheap to toggle and a reader comparing
 * dimensions will hit several in a row, where even a short transition reads as lag.
 */
function SignalRow({ signal }: { signal: AccountSignal }) {
  const [open, setOpen] = useState(false);
  const meta = ACCOUNT_SIGNAL_META[signal.name];
  const score =
    typeof signal.score === 'number'
      ? Math.max(0, Math.min(100, Math.round(signal.score)))
      : null;
  const tier = score === null ? null : signalTier(score);

  return (
    <div className="min-w-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 text-left py-0.5 group"
      >
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-dim flex-1 min-w-0 truncate group-hover:text-fg">
          {meta?.label ?? signal.name}
        </span>
        <span className="w-14 sm:w-16 shrink-0 h-1 bg-bg rounded-full overflow-hidden ring-1 ring-border-1/60">
          {score !== null && tier && (
            <span
              className={cn('block h-full rounded-full', FILL[tier])}
              style={{ width: `${Math.max(2, score)}%` }}
            />
          )}
        </span>
        <span
          className={cn(
            'font-mono text-2xs tabular-nums w-7 text-right shrink-0',
            tier ? TEXT[tier] : 'text-fg-faint',
          )}
        >
          {score === null ? 'n/a' : score}
        </span>
      </button>
      {open && (
        <div className="pb-1.5 space-y-1">
          {signal.reason ? (
            <p className="text-2xs text-fg-dim leading-relaxed">{signal.reason}</p>
          ) : (
            <p className="text-2xs text-fg-faint leading-relaxed italic">
              No reading was returned for this dimension.
            </p>
          )}
          {meta && <p className="text-2xs text-fg-faint leading-relaxed">{meta.description}</p>}
        </div>
      )}
    </div>
  );
}

/**
 * The eight-dimension breakdown behind one account's OMI score, plus how much evidence that read
 * rests on.
 *
 * Every account carries all eight in the same order (the backend normalises whatever the model
 * sent), so the grid reads as one consistent profile down a page of accounts rather than a ragged
 * per-account list. Renders nothing at all for an assessment generated before per-signal scoring
 * shipped, rather than inventing eight empty rows for it.
 */
export function SignalBreakdown({
  signals,
  confidence,
  className,
}: {
  signals?: AccountSignal[];
  confidence?: number;
  className?: string;
}) {
  const rows = (signals ?? []).filter((s) => s && ACCOUNT_SIGNAL_META[s.name]);
  if (rows.length === 0) return null;
  const conf =
    typeof confidence === 'number' ? Math.max(0, Math.min(100, Math.round(confidence))) : null;

  return (
    <div className={cn('border-t border-border-1/60 pt-2 space-y-1', className)}>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-mono text-2xs uppercase tracking-[0.18em] text-fg-mute">
          Signal breakdown
        </span>
        {conf !== null && (
          <span
            className="font-mono text-2xs text-fg-faint ml-auto tabular-nums"
            title="How much evidence this account's read rests on."
          >
            confidence {conf}%
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5">
        {rows.map((s) => (
          <SignalRow key={s.name} signal={s} />
        ))}
      </div>
      <p className="text-2xs text-fg-faint leading-relaxed pt-0.5">
        0 reads like a real person, 100 is a strong bought tell. Tap a dimension for the reason.
      </p>
    </div>
  );
}
