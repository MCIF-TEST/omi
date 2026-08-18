'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/cn';
import { type Tier } from '@/lib/api';

interface ScoreRingProps {
  /** 0..1 probability. */
  value: number;
  tier?: Tier | null;
  size?: number;
  /** Stroke thickness. */
  stroke?: number;
  className?: string;
  /** Hide the percentage label in the centre. */
  hideLabel?: boolean;
}

const RING: Record<Tier | 'none', string> = {
  low:      'var(--tier-low)',
  moderate: 'var(--tier-moderate)',
  elevated: 'var(--tier-elevated)',
  high:     'var(--tier-high)',
  none:     'var(--accent)',
};

/**
 * Circular probability gauge. The stroke sweeps to its value with an ease-out
 * curve when it enters view.
 *
 * Read as an instrument, not as a progress donut: a graduated tick ring outside
 * the track, a butt-capped arc that starts and ends exactly on its value, and no
 * glow. The rounded cap was overhanging the reading by half a stroke at each
 * end, which on a 96px ring is about two points of score, and the filter was
 * `drop-shadow(0 0 6px var(--tier-low)66)`: a CSS variable with two characters
 * concatenated onto it, so it was never a valid colour and never painted
 * anything. It is gone rather than repaired.
 */
export function ScoreRing({
  value,
  tier,
  size = 96,
  stroke = 7,
  className,
  hideLabel = false,
}: ScoreRingProps) {
  const pct = Math.max(0, Math.min(1, value));
  const color = RING[tier ?? 'none'];
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;

  const [progress, setProgress] = useState(0);
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setProgress(pct);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          const start = performance.now();
          const dur = 1000;
          const tick = (now: number) => {
            const t = Math.min(1, (now - start) / dur);
            const eased = 1 - Math.pow(1 - t, 3);
            setProgress(eased * pct);
            if (t < 1) requestAnimationFrame(tick);
          };
          requestAnimationFrame(tick);
          io.disconnect();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [pct]);

  return (
    <div className={cn('relative inline-flex items-center justify-center', className)} style={{ width: size, height: size }}>
      <svg ref={ref} width={size} height={size} className="-rotate-90">
        {/* Graduation. Twenty marks, every fifth one long: the ring becomes a
            scale a reader can estimate against instead of a shape that is
            simply more or less full. Suppressed on small instances, where the
            marks would sit closer together than they can be drawn. */}
        {size >= 64 && (
          <g stroke="var(--border-2)" strokeWidth="1">
            {Array.from({ length: 20 }).map((_, i) => {
              const a = (i / 20) * Math.PI * 2;
              const r0 = r + stroke / 2 + 2;
              const r1 = r0 + (i % 5 === 0 ? 5 : 2.5);
              const c = size / 2;
              return (
                <line key={i}
                  x1={c + Math.cos(a) * r0} y1={c + Math.sin(a) * r0}
                  x2={c + Math.cos(a) * r1} y2={c + Math.sin(a) * r1}
                />
              );
            })}
          </g>
        )}
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="var(--border)" strokeWidth={stroke}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          // Butt cap: the arc has to end ON the value it reports. A round cap
          // adds half a stroke past each end of the sweep, which reads high.
          strokeLinecap="butt"
          strokeDasharray={circ}
          strokeDashoffset={circ * (1 - progress)}
          style={{ transition: 'stroke 0.3s ease' }}
        />
      </svg>
      {!hideLabel && (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-mono font-semibold tabular-nums text-fg" style={{ fontSize: size * 0.26 }}>
            {Math.round(progress * 100)}
          </span>
          <span className="font-mono text-fg-mute" style={{ fontSize: size * 0.11 }}>%</span>
        </div>
      )}
    </div>
  );
}
