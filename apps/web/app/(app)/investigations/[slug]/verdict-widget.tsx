'use client';

import { useState } from 'react';
import { CheckCircle2, ChevronDown } from 'lucide-react';
import { apiClient, type InvestigationVerdict, VERDICT_LABELS } from '@/lib/api';

const VERDICTS: InvestigationVerdict[] = [
  'confirmed_bot_ring',
  'likely_inauthentic',
  'mixed',
  'likely_authentic',
  'inconclusive',
];

const VERDICT_TONES: Record<InvestigationVerdict, string> = {
  pending: 'text-fg-mute border-border-2',
  confirmed_bot_ring: 'text-tier-high border-tier-high/50 bg-tier-high/10',
  likely_inauthentic: 'text-tier-elevated border-tier-elevated/50 bg-tier-elevated/10',
  mixed: 'text-tier-moderate border-tier-moderate/50 bg-tier-moderate/10',
  likely_authentic: 'text-tier-low border-tier-low/50 bg-tier-low/10',
  inconclusive: 'text-fg-mute border-border-2',
};

interface Props {
  slug: string;
  initialVerdict: InvestigationVerdict | null;
  initialNotes: string | null;
}

export function VerdictWidget({ slug, initialVerdict, initialNotes }: Props) {
  const [verdict, setVerdict] = useState<InvestigationVerdict | null>(initialVerdict);
  const [notes, setNotes] = useState(initialNotes ?? '');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const save = async (newVerdict: InvestigationVerdict | null, newNotes?: string) => {
    setSaving(true);
    setSaved(false);
    try {
      await apiClient(`/v1/investigations/${slug}`, {
        method: 'PATCH',
        body: JSON.stringify({
          verdict: newVerdict ?? 'pending',
          notes: newNotes !== undefined ? newNotes : notes,
        }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch { /* no-op */ }
    setSaving(false);
  };

  const selectVerdict = async (v: InvestigationVerdict) => {
    const next = verdict === v ? null : v;
    setVerdict(next);
    setOpen(false);
    await save(next);
  };

  const saveNotes = async () => {
    await save(verdict, notes);
  };

  const current = verdict ?? 'pending';
  const tone = VERDICT_TONES[current];

  return (
    <div className="space-y-3">
      {/* Verdict picker */}
      <div className="relative">
        <button
          onClick={() => setOpen(!open)}
          className={`w-full flex items-center justify-between gap-3 px-4 py-3 rounded-sm border text-left transition-colors ${tone}`}
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 size={14} />
            <span className="font-mono text-xs tracking-wider uppercase">
              {VERDICT_LABELS[current]}
            </span>
          </div>
          <div className="flex items-center gap-2">
            {saving && <span className="text-xs text-fg-mute animate-pulse">saving…</span>}
            {saved && <span className="text-xs text-tier-low">saved ✓</span>}
            <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
          </div>
        </button>

        {open && (
          <div className="absolute top-full left-0 right-0 z-50 mt-1 bg-bg-elev border border-border-2 rounded-sm shadow-lg overflow-hidden">
            {VERDICTS.map((v) => (
              <button
                key={v}
                onClick={() => selectVerdict(v)}
                className={`w-full text-left px-4 py-2.5 text-sm font-mono tracking-wider hover:bg-bg-elev-2/60 transition-colors flex items-center gap-2 ${
                  verdict === v ? 'text-accent' : 'text-fg-dim'
                }`}
              >
                {verdict === v && <CheckCircle2 size={12} className="text-accent" />}
                {verdict !== v && <span className="w-3" />}
                {VERDICT_LABELS[v]}
              </button>
            ))}
            {verdict && (
              <button
                onClick={() => selectVerdict(verdict)}
                className="w-full text-left px-4 py-2.5 text-xs font-mono tracking-wider text-fg-mute hover:bg-bg-elev-2/60 transition-colors border-t border-border-1"
              >
                Clear verdict
              </button>
            )}
          </div>
        )}
      </div>

      {/* Notes textarea */}
      <div>
        <label className="font-mono text-2xs tracking-wider uppercase text-fg-mute block mb-1.5">
          Analyst notes (private)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          onBlur={saveNotes}
          placeholder="Add context, links, observations…"
          rows={3}
          className="w-full px-3 py-2.5 bg-bg border border-border-2 rounded-sm text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent resize-none"
        />
      </div>
    </div>
  );
}
