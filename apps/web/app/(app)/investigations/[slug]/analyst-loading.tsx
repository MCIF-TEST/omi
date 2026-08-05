'use client';

import { Brain } from 'lucide-react';

// The stages the analyst actually works through in its single pass over the evidence. Shown as an
// honest description of the work, not fabricated per-step completion, a soft sweep passes over the
// list so the panel reads as alive while the one model call runs.
const STAGES = [
  'Reading the raw evidence for every account',
  'Scoring each account on its own evidence',
  'Checking for coordination across accounts',
  'Writing each verdict in plain English',
];

/**
 * The AI-analysis loading screen. It appears the moment an investigation opens and stays until the
 * model response lands, so a two-minute read feels deliberate rather than broken. Blue is the
 * identity; purple marks the AI. No glow, no glass.
 */
export function AnalystLoading({
  elapsedSec,
  retrying = false,
}: {
  elapsedSec: number;
  retrying?: boolean;
}) {
  const slow = elapsedSec >= 75;
  return (
    <div className="rounded-lg border border-border-1 bg-bg-elev-2/50 overflow-hidden">
      {/* Header. Real state + real elapsed time (no fake percentage) */}
      <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-divider">
        <span className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-2 animate-pulse-dot" />
          <span className="font-mono text-2xs tracking-[0.16em] uppercase text-violet-2">
            {retrying ? 'Omi analyst · retrying' : 'Omi analyst · running'}
          </span>
        </span>
        <span className="font-mono text-2xs text-fg-mute tabular-nums">{elapsedSec}s</span>
      </div>

      <div className="p-5 space-y-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 shrink-0 grid place-items-center w-8 h-8 rounded-md bg-violet-solid/15 border border-violet-solid/40">
            <Brain size={15} className="text-violet-2" />
          </span>
          <div className="min-w-0">
            <p className="text-sm text-fg leading-relaxed">
              Omi is reading this investigation and scoring every account on its own evidence.
            </p>
            <p className="text-xs text-fg-mute leading-relaxed mt-0.5">
              It writes each verdict in plain English. Large scans are analysed in batches of 25, one
              pass each, so a full read can take up to 10 minutes. Accounts appear as each batch
              lands, and you do not need to stay on this page.
            </p>
          </div>
        </div>

        {/* Indeterminate bar. Blue, honest: it moves while the call runs, it claims no known percentage */}
        <div className="h-1 rounded-full bg-bg-inset overflow-hidden" role="progressbar" aria-label="AI analysis in progress">
          <div className="analyst-indeterminate h-full w-1/3 rounded-full bg-accent" />
        </div>

        {/* The stages the analyst works through, a soft sweep marks the moving focus */}
        <ol className="space-y-2 analyst-sweep">
          {STAGES.map((s, i) => (
            <li key={i} className="flex items-center gap-2.5 text-fg-mute" style={{ ['--i' as string]: i }}>
              <span className="stage-dot w-1.5 h-1.5 rounded-full bg-border-hot shrink-0" />
              <span className="text-sm leading-snug">{s}</span>
            </li>
          ))}
        </ol>

        {slow && (
          <p className="font-mono text-2xs text-fg-faint leading-relaxed border-t border-divider pt-3">
            Still working. Large investigations take longer because the analyst reads every account
            individually. This screen updates on its own the moment the result lands.
          </p>
        )}
      </div>

      <style jsx>{`
        .analyst-indeterminate {
          animation: analyst-slide 1.4s ease-in-out infinite;
        }
        @keyframes analyst-slide {
          0% { transform: translateX(-120%); }
          100% { transform: translateX(420%); }
        }
        .analyst-sweep .stage-dot {
          animation: stage-pulse 3.2s ease-in-out infinite;
          animation-delay: calc(var(--i) * 0.5s);
        }
        @keyframes stage-pulse {
          0%, 100% { background: var(--border-hot); transform: scale(1); }
          20% { background: var(--accent); transform: scale(1.5); }
        }
        @media (prefers-reduced-motion: reduce) {
          .analyst-indeterminate { animation: none; width: 100%; opacity: 0.5; }
          .analyst-sweep .stage-dot { animation: none; }
        }
      `}</style>
    </div>
  );
}
