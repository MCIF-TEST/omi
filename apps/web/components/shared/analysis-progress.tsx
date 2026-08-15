'use client';

import { Brain, Radar } from 'lucide-react';
import { batchesFor, displayedBatch, formatElapsed } from '@/lib/analysis-progress';

/**
 * The ONE progress screen for a running investigation.
 *
 * There used to be three, and they read as three different things happening rather than one job
 * making progress: a violet "Analyzing N accounts" card on the select page, a grey skeleton while
 * the investigation route loaded, then a separate analyst card with stages and a bar. A user who
 * has just spent a credit watched the screen change shape twice and could not tell whether that was
 * progress or a restart.
 *
 * This component is all three. The compile and select steps before it are unchanged.
 */

const STAGES: Record<Phase, string[]> = {
  scanning: [
    'Pulling each account’s profile and history',
    'Scoring every account on its own evidence',
    'Checking for coordination across accounts',
    'Writing each verdict in plain English',
  ],
  analysing: [
    'Reading the raw evidence for every account',
    'Scoring each account on its own evidence',
    'Checking for coordination across accounts',
    'Writing each verdict in plain English',
  ],
};

export type Phase = 'scanning' | 'analysing';

export function AnalysisProgress({
  elapsedSec,
  accounts,
  totalBatches,
  phase = 'analysing',
  retrying = false,
}: {
  elapsedSec: number;
  /** How many accounts are being analysed. Used to derive the batch count when it is not passed. */
  accounts?: number;
  /** Overrides the derived count when the server has already told us the real total. */
  totalBatches?: number;
  phase?: Phase;
  retrying?: boolean;
}) {
  const total = totalBatches ?? batchesFor(accounts ?? 0);
  const current = displayedBatch(elapsedSec, total);
  const slow = elapsedSec >= 75;

  return (
    <div className="rounded-lg border border-border-1 bg-bg-elev-2/50 overflow-hidden">
      {/* Real state and a real elapsed clock. No fabricated percentage. */}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-divider">
        <span className="flex items-center gap-2 min-w-0">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-2 animate-pulse-dot shrink-0" />
          <span className="font-mono text-2xs tracking-[0.16em] uppercase text-violet-2 truncate">
            {retrying ? 'Omi analyst · retrying' : 'Omi analyst · running'}
          </span>
        </span>
        <span className="font-mono text-2xs text-fg-mute tabular-nums shrink-0">{formatElapsed(elapsedSec)}</span>
      </div>

      <div className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 shrink-0 grid place-items-center w-8 h-8 rounded-md bg-violet-solid/15 border border-violet-solid/40">
            {phase === 'scanning'
              ? <Radar size={15} className="text-violet-2" />
              : <Brain size={15} className="text-violet-2" />}
          </span>
          <div className="min-w-0">
            <p className="text-sm text-fg leading-relaxed">
              {total > 1
                ? <>Analysing batch <span className="font-mono tabular-nums">{current}</span> of{' '}
                   <span className="font-mono tabular-nums">{total}</span>.</>
                : <>Analysing {accounts ? `${accounts} ` : ''}
                   account{accounts === 1 ? '' : 's'}.</>}
              {' '}Omi scores every account on its own evidence.
            </p>
            <p className="text-xs text-fg-mute leading-relaxed mt-0.5">
              {total > 1
                ? `Your selection is split into ${total} passes of roughly equal size, so a full read can take up to 10 minutes. Accounts appear as each batch lands, and you do not need to stay on this page.`
                : 'It writes each verdict in plain English. This usually takes a couple of minutes, and you do not need to stay on this page.'}
            </p>
          </div>
        </div>

        {/* Batch position, one segment per pass. Honest about what it is: which batch is being
            worked on, out of how many, not a count of finished ones (nothing has finished yet, or
            this screen would have been replaced by the results). The same track renders on the
            results page once real progress arrives, so the two screens read as one continuous job
            rather than two unrelated loaders. */}
        <div
          className="flex items-center gap-1"
          role="progressbar"
          aria-valuenow={current} aria-valuemin={1} aria-valuemax={total}
          aria-label={`Analysing batch ${current} of ${total}`}
        >
          {Array.from({ length: total }, (_, i) => (
            <div key={i} className="relative h-1.5 flex-1 rounded-full bg-bg-inset overflow-hidden">
              <div
                className={`absolute inset-0 rounded-full bg-violet-dim transition-opacity duration-300 ease-out ${
                  i < current - 1 ? 'opacity-100' : i === current - 1 ? 'opacity-30' : 'opacity-0'
                }`}
              />
              {i === current - 1 && (
                <div
                  className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-violet-2 opacity-0 motion-safe:opacity-70 motion-safe:animate-batch-sweep"
                  aria-hidden
                />
              )}
            </div>
          ))}
        </div>

        <ol className="space-y-2 analyst-sweep">
          {STAGES[phase].map((s, i) => (
            <li key={i} className="flex items-center gap-2.5 text-fg-mute" style={{ ['--i' as string]: i }}>
              <span className="stage-dot w-1.5 h-1.5 rounded-full bg-border-hot shrink-0" />
              <span className="text-sm leading-snug">{s}</span>
            </li>
          ))}
        </ol>

        {slow && (
          <p className="font-mono text-2xs text-fg-faint leading-relaxed border-t border-divider pt-3">
            Still working. Large investigations take longer because the analyst reads every account
            individually. This screen updates on its own the moment results land.
          </p>
        )}
      </div>

      <style jsx>{`
        .analyst-sweep .stage-dot {
          animation: stage-pulse 3.2s ease-in-out infinite;
          animation-delay: calc(var(--i) * 0.5s);
        }
        @keyframes stage-pulse {
          0%, 100% { background: var(--border-hot); transform: scale(1); }
          20% { background: var(--accent); transform: scale(1.5); }
        }
        @media (prefers-reduced-motion: reduce) {
          .analyst-sweep .stage-dot { animation: none; }
        }
      `}</style>
    </div>
  );
}
