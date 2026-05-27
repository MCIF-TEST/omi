import { type Tier } from './api';

export function pct(n: number | null | undefined): string {
  if (n == null) return '—';
  return `${Math.round(n * 100)}%`;
}

export function tierColor(tier: Tier | null | undefined): string {
  switch (tier) {
    case 'high':     return 'text-tier-high';
    case 'elevated': return 'text-tier-elevated';
    case 'moderate': return 'text-tier-moderate';
    case 'low':      return 'text-tier-low';
    default:         return 'text-fg-dim';
  }
}

export function tierBg(tier: Tier | null | undefined): string {
  switch (tier) {
    case 'high':     return 'bg-tier-high/10 border-tier-high/40 text-tier-high';
    case 'elevated': return 'bg-tier-elevated/10 border-tier-elevated/40 text-tier-elevated';
    case 'moderate': return 'bg-tier-moderate/10 border-tier-moderate/40 text-tier-moderate';
    case 'low':      return 'bg-tier-low/10 border-tier-low/40 text-tier-low';
    default:         return 'bg-bg-elev border-border-1 text-fg-dim';
  }
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (!t) return '';
  const secs = Math.max(1, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.round(months / 12)}y ago`;
}
