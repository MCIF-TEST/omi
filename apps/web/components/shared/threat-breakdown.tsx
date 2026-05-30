'use client';

import { useState } from 'react';
import { ChevronDown, ShieldCheck, AlertTriangle, Network, Megaphone, Repeat2, Bot } from 'lucide-react';
import { cn } from '@/lib/cn';
import { THREAT_KEYS, THREAT_META, type OmiScore, type ThreatKey, type IntelligenceDimension } from '@/lib/api';

const RISK_STYLE: Record<OmiScore['risk_level'], { text: string; bg: string; ring: string; label: string }> = {
  high:   { text: 'text-tier-high',     bg: 'bg-tier-high/10 border-tier-high/40',     ring: 'var(--tier-high)',     label: 'High risk' },
  medium: { text: 'text-tier-elevated', bg: 'bg-tier-elevated/10 border-tier-elevated/40', ring: 'var(--tier-elevated)', label: 'Medium risk' },
  low:    { text: 'text-tier-low',      bg: 'bg-tier-low/10 border-tier-low/40',       ring: 'var(--tier-low)',      label: 'Low risk' },
};

const THREAT_ICON: Record<ThreatKey, React.ReactNode> = {
  coordination_probability:  <Network size={13} />,
  amplification_probability: <Megaphone size={13} />,
  spam_probability:          <Repeat2 size={13} />,
  ai_generation_probability: <Bot size={13} />,
};

// Probability (0–100) → tier color, matching the detector-breakdown convention.
function probColor(p: number) {
  if (p >= 75) return { bar: 'bg-tier-high',     text: 'text-tier-high' };
  if (p >= 50) return { bar: 'bg-tier-elevated', text: 'text-tier-elevated' };
  if (p >= 25) return { bar: 'bg-tier-moderate', text: 'text-tier-moderate' };
  return { bar: 'bg-tier-low', text: 'text-tier-low' };
}

export function ThreatBreakdown({ score, className }: { score: OmiScore; className?: string }) {
  const risk = RISK_STYLE[score.risk_level];
  const omi = Math.round(score.omi_score);
  const auth = Math.round(score.authenticity_score);

  return (
    <div className={cn('space-y-5', className)}>
      {/* Headline row: composite OmiScore + risk + authenticity */}
      <div className="relative overflow-hidden rounded-2xl border border-border-1 bg-gradient-to-br from-bg-elev-2/60 to-bg-elev/20 p-5">
        <div className="relative flex items-center gap-5 flex-wrap">
          {/* Composite score dial */}
          <div className="relative shrink-0 w-[88px] h-[88px]">
            <svg viewBox="0 0 88 88" className="w-full h-full -rotate-90">
              <circle cx="44" cy="44" r="38" fill="none" stroke="var(--border)" strokeWidth="7" />
              <circle cx="44" cy="44" r="38" fill="none" stroke={risk.ring} strokeWidth="7" strokeLinecap="round"
                strokeDasharray={`${(omi / 100) * 2 * Math.PI * 38} ${2 * Math.PI * 38}`}
                style={{ filter: `drop-shadow(0 0 6px ${risk.ring}66)`, transition: 'stroke-dasharray 0.9s cubic-bezier(0.16,1,0.3,1)' }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="font-mono text-2xl font-semibold tabular-nums text-fg leading-none">{omi}</span>
              <span className="font-mono text-[0.55rem] tracking-[0.16em] text-fg-mute uppercase mt-0.5">omi</span>
            </div>
          </div>

          <div className="flex-1 min-w-[180px]">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <span className={cn('inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2.5 py-1 rounded-full border', risk.bg, risk.text)}>
                <AlertTriangle size={11} />
                {risk.label}
              </span>
              <span className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2.5 py-1 rounded-full border border-tier-low/40 bg-tier-low/10 text-tier-low">
                <ShieldCheck size={11} />
                {auth}% authentic
              </span>
            </div>
            <p className="text-sm text-fg leading-relaxed">{score.headline}</p>
            <p className="font-mono text-2xs text-fg-faint mt-2 tracking-wider">
              confidence {Math.round(score.confidence * 100)}% · schema v{score.schema_version}
            </p>
          </div>
        </div>
      </div>

      {/* Threat dimension bars */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        {THREAT_KEYS.map((key) => {
          const dim = score.dimensions.find((d) => d.key === key);
          const value = Math.round((score as any)[key] as number);
          const isPrimary = score.primary_threat === key;
          return (
            <ThreatBar
              key={key}
              icon={THREAT_ICON[key]}
              label={THREAT_META[key].short}
              value={value}
              isPrimary={isPrimary}
              dimension={dim}
            />
          );
        })}
      </div>

      {/* Top evidence */}
      {score.top_evidence.length > 0 && (
        <div>
          <div className="font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-2">
            Top evidence
          </div>
          <ul className="space-y-1.5">
            {score.top_evidence.slice(0, 6).map((e, i) => (
              <li key={i} className="text-sm text-fg-dim leading-relaxed pl-3 border-l border-border-2">
                {e}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ThreatBar({
  icon, label, value, isPrimary, dimension,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  isPrimary: boolean;
  dimension?: IntelligenceDimension;
}) {
  const [open, setOpen] = useState(false);
  const { bar, text } = probColor(value);
  const hasDetail = (dimension?.contributions.length ?? 0) > 0;

  return (
    <div className={cn(
      'rounded-xl border p-3.5 transition-colors',
      isPrimary ? 'border-tier-high/40 bg-tier-high/[0.05]' : 'border-border-1 bg-bg',
    )}>
      <button
        type="button"
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={cn('w-full text-left', hasDetail && 'cursor-pointer')}
        aria-expanded={open}
      >
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider text-fg-dim">
            <span className={text}>{icon}</span>
            {label}
            {isPrimary && (
              <span className="font-mono text-[0.55rem] tracking-wider text-tier-high border border-tier-high/40 bg-tier-high/10 rounded-full px-1.5 py-px">
                primary
              </span>
            )}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <span className={cn('font-mono font-bold text-sm tabular-nums', text)}>{value}%</span>
            {hasDetail && (
              <ChevronDown size={13} className={cn('text-fg-mute transition-transform', open && 'rotate-180')} />
            )}
          </span>
        </div>
        <div className="h-1.5 w-full bg-border-1 rounded-full overflow-hidden">
          <div
            className={cn('h-full rounded-full bar-fill transition-[width] duration-700 ease-omi', bar)}
            style={{ width: `${value}%` }}
          />
        </div>
      </button>

      {open && dimension && (
        <div className="mt-3 pt-3 border-t border-border-1/60 space-y-2.5">
          <p className="text-2xs text-fg-mute leading-relaxed">{dimension.description}</p>
          {dimension.contributions.map((c) => (
            <div key={c.detector} className="text-2xs">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-mono text-fg-dim uppercase tracking-wider">{c.label}</span>
                <span className="font-mono text-fg-mute">
                  {Math.round(c.weight_share * 100)}% share · conf {Math.round(c.confidence * 100)}%
                </span>
              </div>
              {c.evidence[0] && (
                <p className="text-fg-mute leading-relaxed">{c.evidence[0]}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
