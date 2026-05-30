import { describe, it, expect } from 'vitest';
import { pct, tierColor, tierBg, timeAgo } from './format';

describe('pct', () => {
  it('renders an em dash for null/undefined', () => {
    expect(pct(null)).toBe('—');
    expect(pct(undefined)).toBe('—');
  });
  it('rounds a 0..1 ratio to a percent', () => {
    expect(pct(0)).toBe('0%');
    expect(pct(0.5)).toBe('50%');
    expect(pct(0.834)).toBe('83%');
    expect(pct(1)).toBe('100%');
  });
});

describe('tierColor / tierBg', () => {
  it('maps each tier to its token and falls back for unknown', () => {
    expect(tierColor('high')).toContain('tier-high');
    expect(tierColor('low')).toContain('tier-low');
    expect(tierColor(null)).toBe('text-fg-dim');
    expect(tierBg('elevated')).toContain('tier-elevated');
    expect(tierBg(undefined)).toContain('bg-bg-elev');
  });
});

describe('timeAgo', () => {
  it('returns empty string for missing or unparseable input', () => {
    expect(timeAgo(null)).toBe('');
    expect(timeAgo('')).toBe('');
    expect(timeAgo('not-a-date')).toBe('');
  });

  it('formats recent times with the coarsest sensible unit', () => {
    const ago = (ms: number) => new Date(Date.now() - ms).toISOString();
    expect(timeAgo(ago(5_000))).toMatch(/^\d+s ago$/);
    expect(timeAgo(ago(5 * 60_000))).toMatch(/^\d+m ago$/);
    expect(timeAgo(ago(5 * 3_600_000))).toMatch(/^\d+h ago$/);
    expect(timeAgo(ago(3 * 86_400_000))).toMatch(/^\d+d ago$/);
    expect(timeAgo(ago(60 * 86_400_000))).toMatch(/^\d+mo ago$/);
    expect(timeAgo(ago(400 * 86_400_000))).toMatch(/^\d+y ago$/);
  });
});
