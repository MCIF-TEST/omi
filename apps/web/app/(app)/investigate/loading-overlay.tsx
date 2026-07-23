'use client';

import { useEffect, useState } from 'react';

// What a scan runs, in order. Shown as an honest description of the pipeline —
// NOT as steps that "complete" on a timer. The backend reports a coarse job
// state (queued → running → done), so we surface that real state + the real
// elapsed time rather than fabricating per-step progress.
const PIPELINE = [
  'Resolve the link',
  'Fetch commenters / repliers',
  'Pull each account’s history',
  'Run the detection engine',
  'Compute cross-account coordination',
  'Build the synthesis',
];

type JobStatus = 'queued' | 'running' | 'done' | 'failed' | null | undefined;

export function LoadingOverlay({ active, status }: { active: boolean; status?: JobStatus }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) return;
    setElapsed(0);
    const start = Date.now();
    const tick = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 250);
    return () => clearInterval(tick);
  }, [active]);

  if (!active) return null;

  const queued = status === 'queued';
  const label = queued ? 'Queued' : 'Scanning';
  const detail = queued
    ? 'Your scan is queued on the backend and will start in a moment.'
    : 'Omi is fetching accounts and running the detection + coordination engines on the backend.';

  return (
    <div className="rounded-2xl border border-border-1 bg-bg overflow-hidden animate-fade-up shadow-card-lg">
      {/* Header: REAL job state + REAL elapsed time */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border-1 bg-bg-elev/60">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot" />
          <span className="font-mono text-2xs tracking-[0.2em] text-accent uppercase">{label}</span>
        </div>
        <span className="font-mono text-2xs text-fg-mute tabular-nums">{elapsed}s elapsed</span>
      </div>

      <div className="flex flex-col sm:flex-row gap-8 p-6 items-start sm:items-center">
        {/* Indeterminate "working" gauge — honest: it spins while the job runs,
            it does not claim a known percentage. */}
        <div className="relative shrink-0 w-28 h-28 mx-auto sm:mx-0">
          <svg viewBox="0 0 112 112" className="w-full h-full -rotate-90">
            <circle cx="56" cy="56" r="50" stroke="rgba(59,130,246,0.14)" strokeWidth="1.5" fill="none" />
            <circle cx="56" cy="56" r="50" stroke="#3b82f6" strokeWidth="1.5" fill="none"
              strokeDasharray="28 290"
              style={{ transformOrigin: '56px 56px', animation: 'hv-radar 2.8s linear infinite' }}
            />
            <circle cx="56" cy="56" r="36" stroke="rgba(143,123,240,0.22)" strokeWidth="1" fill="none" />
            <circle cx="56" cy="56" r="36" stroke="#8f7bf0" strokeWidth="1" fill="none"
              strokeDasharray="18 207"
              style={{ transformOrigin: '56px 56px', animation: 'hv-radar 2s linear infinite reverse' }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-accent/50 animate-pulse-dot" />
          </div>
        </div>

        {/* Honest description of the pipeline (not fake per-step completion). */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-fg-dim leading-relaxed mb-3">{detail}</p>
          <ol className="space-y-1.5">
            {PIPELINE.map((p, i) => (
              <div key={i} className="flex items-center gap-2.5 text-fg-mute">
                <span className="font-mono text-2xs text-fg-faint tabular-nums w-4">{i + 1}</span>
                <span className="text-sm leading-snug">{p}</span>
              </div>
            ))}
          </ol>
        </div>
      </div>

      <div className="px-5 py-3 border-t border-border-1/50 bg-bg-elev/30">
        <p className="font-mono text-2xs text-fg-faint leading-relaxed">
          Live per-step progress isn’t reported — this shows the real job state and elapsed
          time. 15–45s typical · cached commenters return instantly on re-scan.
        </p>
      </div>
    </div>
  );
}
