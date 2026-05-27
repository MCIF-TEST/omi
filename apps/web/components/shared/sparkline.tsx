/**
 * Minimal SVG sparkline. No dependencies; renders inline.
 * Tier-tinted: the curve color follows the latest tier.
 */
import { type Tier } from '@/lib/api';

interface SparklineProps {
  points: number[]; // 0..1 values, oldest → newest
  tier?: Tier;
  height?: number;
  className?: string;
}

const tierStroke: Record<Tier, string> = {
  low: '#10b981',
  moderate: '#f59e0b',
  elevated: '#fb923c',
  high: '#ef4444',
};

export function Sparkline({ points, tier, height = 64, className }: SparklineProps) {
  if (!points.length) return null;
  const W = 240;
  const H = height;
  const padX = 4;
  const padY = 6;
  const xs = points.map((_, i) => padX + (i * (W - 2 * padX)) / Math.max(1, points.length - 1));
  const ys = points.map((p) => padY + (1 - p) * (H - 2 * padY));
  const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');

  const stroke = tier ? tierStroke[tier] : 'var(--accent)';
  const lastX = xs[xs.length - 1];
  const lastY = ys[ys.length - 1];

  return (
    <svg
      className={className}
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      height={H}
      preserveAspectRatio="none"
      aria-hidden
    >
      {/* Gridline at 0.5 */}
      <line
        x1={0} x2={W}
        y1={padY + 0.5 * (H - 2 * padY)}
        y2={padY + 0.5 * (H - 2 * padY)}
        stroke="var(--border)"
        strokeDasharray="2 3"
      />
      {/* Path */}
      <path
        d={d}
        fill="none"
        stroke={stroke}
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Latest point */}
      <circle cx={lastX} cy={lastY} r={3} fill={stroke} />
    </svg>
  );
}
