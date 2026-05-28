'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, BarChart2 } from 'lucide-react';
import type { HistoricalScan, SignalResult } from '@/lib/api';
import { pct, timeAgo, tierBg } from '@/lib/format';

const SIGNAL_LABELS: Record<string, string> = {
  temporal:    'Posting cadence',
  semantic:    'Content repetition',
  ai_writing:  'AI-writing patterns',
  profile:     'Profile metadata',
  voice:       'Personal voice',
  engagement:  'Engagement farming',
  memory:      'Fingerprint match',
  coordination:'Coordination cluster',
};

interface Props {
  scan: HistoricalScan;
  defaultOpen?: boolean;
}

export function HistoryRow({ scan: s, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const signals = (s.signals ?? []).filter((sig) => sig.confidence > 0);
  const canExpand = signals.length > 0;

  return (
    <>
      <tr
        className={`border-b border-border-1 hover:bg-bg-elev/50 transition-colors ${
          canExpand ? 'cursor-pointer' : ''
        }`}
        onClick={() => canExpand && setOpen((v) => !v)}
      >
        <td className="px-2 py-3 font-mono text-2xs text-fg-dim whitespace-nowrap">
          <span className="inline-flex items-center gap-1">
            {canExpand ? (
              open ? <ChevronDown size={11} /> : <ChevronRight size={11} />
            ) : (
              <span className="inline-block w-[11px]" />
            )}
            {timeAgo(s.scanned_at)}
          </span>
        </td>
        <td className="px-2 py-3">
          <span
            className={`inline-block px-2 py-0.5 rounded-sm border font-mono text-2xs uppercase tracking-wider ${tierBg(
              s.tier,
            )}`}
          >
            {s.tier}
          </span>
        </td>
        <td className="px-2 py-3 mono text-right">{pct(s.overall_probability)}</td>
        <td className="px-2 py-3 mono text-right text-fg-dim">{pct(s.confidence)}</td>
        <td className="px-2 py-3 text-fg-dim text-xs leading-relaxed max-w-md">{s.summary}</td>
      </tr>
      {open && (
        <tr className="border-b border-border-1 bg-bg/30">
          <td colSpan={5} className="px-4 py-4">
            <div className="flex items-center gap-1.5 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-3">
              <BarChart2 size={11} />
              Detector breakdown · {timeAgo(s.scanned_at)}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {signals.map((sig) => (
                <SignalCard key={sig.name} signal={sig} />
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SignalCard({ signal }: { signal: SignalResult }) {
  const prob = signal.probability ?? 0;
  const conf = signal.confidence ?? 0;
  const label = SIGNAL_LABELS[signal.name] ?? signal.name;
  const topEvidence = signal.evidence?.[0];
  const barColor =
    prob >= 0.75 ? 'bg-tier-high' :
    prob >= 0.5  ? 'bg-tier-elevated' :
    prob >= 0.25 ? 'bg-tier-moderate' :
    'bg-tier-low';
  const textColor =
    prob >= 0.75 ? 'text-tier-high' :
    prob >= 0.5  ? 'text-tier-elevated' :
    prob >= 0.25 ? 'text-tier-moderate' :
    'text-tier-low';

  return (
    <div className="bg-bg-elev border border-border-1 rounded-sm p-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">{label}</span>
        <span className={`font-mono font-bold text-sm ${textColor}`}>
          {Math.round(prob * 100)}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-border-1 rounded-full overflow-hidden mb-2">
        <div
          className={`h-full rounded-full ${barColor}`}
          style={{ width: `${Math.round(prob * 100)}%`, opacity: Math.max(0.35, conf) }}
        />
      </div>
      <div className="flex items-center justify-between text-2xs font-mono text-fg-faint">
        <span className="truncate max-w-[180px]">{topEvidence ?? 'No evidence noted.'}</span>
        <span className="shrink-0 ml-2">conf {Math.round(conf * 100)}%</span>
      </div>
    </div>
  );
}
