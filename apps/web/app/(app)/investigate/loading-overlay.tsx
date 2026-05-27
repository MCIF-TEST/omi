'use client';

import { useEffect, useState } from 'react';

const PHASES = [
  'Resolving URL…',
  'Fetching commenters from YouTube…',
  'Pulling each commenter\'s recent history…',
  'Running detection engine…',
  'Computing cross-account coordination…',
  'Building cross-links + synthesis…',
];

/**
 * Phased loading state. The backend doesn't stream progress yet so we
 * cycle through plausible phases on a fixed cadence — feels alive,
 * matches reality (each phase IS happening in order), and the final
 * "Building synthesis" sticks until the response arrives.
 */
export function LoadingOverlay({ active }: { active: boolean }) {
  const [phase, setPhase] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) return;
    setPhase(0);
    setElapsed(0);
    const start = Date.now();
    const phaseInterval = setInterval(
      () => setPhase((p) => Math.min(p + 1, PHASES.length - 1)),
      3500,
    );
    const tick = setInterval(
      () => setElapsed(Math.round((Date.now() - start) / 1000)),
      250,
    );
    return () => {
      clearInterval(phaseInterval);
      clearInterval(tick);
    };
  }, [active]);

  if (!active) return null;

  return (
    <div className="rounded-md border border-border-1 bg-bg-elev p-6 animate-fade-up">
      <div className="flex items-baseline justify-between mb-4">
        <span className="font-mono text-2xs tracking-[0.18em] text-accent uppercase">
          Scan in progress
        </span>
        <span className="font-mono text-2xs text-fg-mute tracking-wider">
          {elapsed}s elapsed
        </span>
      </div>
      <div className="space-y-2">
        {PHASES.map((p, i) => {
          const done = i < phase;
          const current = i === phase;
          return (
            <div key={i} className="flex items-center gap-3">
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  done ? 'bg-accent' : current ? 'bg-accent animate-pulse-dot' : 'bg-border-2'
                }`}
              />
              <span
                className={`text-sm ${
                  done ? 'text-fg-dim' : current ? 'text-fg' : 'text-fg-mute'
                }`}
              >
                {p}
              </span>
              {current && (
                <span className="ml-auto font-mono text-2xs text-fg-mute tracking-wider">
                  running…
                </span>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-4 text-2xs text-fg-mute font-mono leading-relaxed">
        Scans take 15–45 seconds depending on batch size and YouTube API
        latency. Cached commenters return instantly on re-scan.
      </p>
    </div>
  );
}
