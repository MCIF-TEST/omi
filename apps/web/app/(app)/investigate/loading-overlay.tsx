'use client';

import { useEffect, useState } from 'react';
import { Check } from 'lucide-react';

const PHASES = [
  'Resolving URL…',
  'Fetching commenters from YouTube…',
  'Pulling commenter history…',
  'Running detection engine…',
  'Computing cross-account coordination…',
  'Building synthesis…',
];

export function LoadingOverlay({ active }: { active: boolean }) {
  const [phase, setPhase]     = useState(0);
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
    return () => { clearInterval(phaseInterval); clearInterval(tick); };
  }, [active]);

  if (!active) return null;

  const pct = Math.round((phase / (PHASES.length - 1)) * 100);

  return (
    <div className="rounded-2xl border border-border-1 bg-bg overflow-hidden animate-fade-up shadow-card-lg">
      {/* Header bar */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-border-1 bg-bg-elev/60">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-full bg-accent animate-pulse-dot" />
          <span className="font-mono text-2xs tracking-[0.2em] text-accent uppercase">Scan in progress</span>
        </div>
        <span className="font-mono text-2xs text-fg-mute tabular-nums">{elapsed}s elapsed</span>
      </div>

      {/* Body: rings + phases */}
      <div className="flex flex-col sm:flex-row gap-8 p-6 items-start sm:items-center">

        {/* Animated ring gauge */}
        <div className="relative shrink-0 w-28 h-28 mx-auto sm:mx-0">
          <svg viewBox="0 0 112 112" className="w-full h-full -rotate-90">
            {/* Outer ring — rotates */}
            <circle cx="56" cy="56" r="50" stroke="rgba(59,142,255,0.10)" strokeWidth="1.5" fill="none" />
            <circle cx="56" cy="56" r="50" stroke="#3b8eff" strokeWidth="1.5" fill="none"
              strokeDasharray="28 290"
              style={{ transformOrigin: '56px 56px', animation: 'hv-radar 2.8s linear infinite' }}
            />
            {/* Middle ring — rotates opposite */}
            <circle cx="56" cy="56" r="36" stroke="rgba(139,92,246,0.18)" strokeWidth="1" fill="none" />
            <circle cx="56" cy="56" r="36" stroke="#8b5cf6" strokeWidth="1" fill="none"
              strokeDasharray="18 207"
              style={{ transformOrigin: '56px 56px', animation: 'hv-radar 2s linear infinite reverse' }}
            />
            {/* Progress arc */}
            <circle cx="56" cy="56" r="22"
              stroke="rgba(59,142,255,0.15)" strokeWidth="6" fill="none"
              strokeDasharray="138"
            />
            <circle cx="56" cy="56" r="22"
              stroke="#3b8eff" strokeWidth="6" fill="none"
              strokeLinecap="round"
              strokeDasharray={`${(pct / 100) * 138} 138`}
              style={{ transition: 'stroke-dasharray 0.8s cubic-bezier(0.16,1,0.3,1)' }}
            />
          </svg>
          {/* Center: percentage */}
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5">
            <span className="font-mono text-lg font-semibold text-accent leading-none">{pct}%</span>
          </div>
          {/* Center hub pulse */}
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <span className="w-2.5 h-2.5 rounded-full bg-accent/40 animate-pulse-dot" />
          </div>
        </div>

        {/* Phase checklist */}
        <div className="flex-1 space-y-2.5 min-w-0">
          {PHASES.map((p, i) => {
            const done    = i < phase;
            const current = i === phase;
            return (
              <div
                key={i}
                className="flex items-center gap-3 transition-opacity duration-300"
                style={{ opacity: done ? 0.45 : current ? 1 : 0.28 }}
              >
                <span className={`shrink-0 flex items-center justify-center w-5 h-5 rounded-full border transition-colors ${
                  done    ? 'bg-accent/20 border-accent/50 text-accent'
                  : current ? 'bg-accent/[0.08] border-accent/40'
                  : 'border-border-2'
                }`}>
                  {done
                    ? <Check size={10} strokeWidth={3} />
                    : current
                      ? <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-dot" />
                      : null}
                </span>
                <span className={`text-sm leading-snug ${
                  done ? 'text-fg-mute line-through decoration-fg-faint/60' : current ? 'text-fg font-medium' : 'text-fg-mute'
                }`}>
                  {p}
                </span>
                {current && (
                  <span className="ml-auto shrink-0 font-mono text-2xs text-accent-dim tracking-wider">
                    running
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer note */}
      <div className="px-5 py-3 border-t border-border-1/50 bg-bg-elev/30">
        <p className="font-mono text-2xs text-fg-faint leading-relaxed">
          15–45s depending on batch size · cached commenters return instantly on re-scan
        </p>
      </div>
    </div>
  );
}
