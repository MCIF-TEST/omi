'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  Loader2,
  Play,
  AlertCircle,
  ArrowRight,
  ShieldAlert,
  Users,
  Network,
  Flame,
  Shield,
  AlertTriangle,
} from 'lucide-react';
import { apiClient, ApiError, type ComprehensiveScanResult } from '@/lib/api';
import { ScoreRing } from '@/components/shared/score-ring';

const EXAMPLES = [
  'https://www.youtube.com/watch?v=jNQXAC9IVRw',
  'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
];

const TIER_COLOR: Record<string, string> = {
  high: 'text-tier-high border-tier-high/40 bg-tier-high/10',
  elevated: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
  moderate: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
  low: 'text-tier-low border-tier-low/40 bg-tier-low/10',
};

const TIER_ICON: Record<string, React.ReactNode> = {
  high: <Flame size={12} />,
  elevated: <ShieldAlert size={12} />,
  moderate: <AlertTriangle size={12} />,
  low: <Shield size={12} />,
};

export function DemoScanForm() {
  const [url, setUrl] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ComprehensiveScanResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [phase, setPhase] = useState(0);

  async function runDemo(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) return;
    setBusy(true);
    setErr(null);
    setResult(null);
    setPhase(0);
    const phaseTimer = setInterval(() => setPhase((p) => Math.min(p + 1, 4)), 2000);

    try {
      const body = await apiClient<ComprehensiveScanResult>('/v1/scan/demo', {
        method: 'POST',
        body: JSON.stringify({ url: url.trim() }),
      });
      setResult(body);
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 429) setErr(e.message);
        else if (e.status === 400) setErr(e.message);
        else setErr(e.message || 'Scan failed.');
      } else {
        setErr('Network error.');
      }
    } finally {
      clearInterval(phaseTimer);
      setBusy(false);
    }
  }

  if (result) {
    return <DemoResult result={result} onReset={() => { setResult(null); setUrl(''); }} />;
  }

  return (
    <div className="space-y-4">
      <form onSubmit={runDemo} className="flex gap-2 flex-wrap">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=…"
          disabled={busy}
          required
          className="flex-1 min-w-[280px] px-4 py-3 bg-bg border border-border-1 rounded-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={busy || !url.trim()}
          className="inline-flex items-center gap-2 bg-accent text-bg-deep font-medium px-5 py-3 rounded-sm hover:bg-accent-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
          {busy ? 'Scanning…' : 'Run free scan'}
        </button>
      </form>

      {!busy && !err && (
        <div className="flex items-center gap-2 flex-wrap font-mono text-2xs text-fg-mute">
          <span>Try:</span>
          {EXAMPLES.map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => setUrl(u)}
              className="text-accent hover:underline truncate max-w-[280px]"
            >
              {u.replace('https://www.youtube.com/', '')}
            </button>
          ))}
        </div>
      )}

      {busy && (
        <div className="space-y-1.5 pt-2">
          {[
            'Fetching commenters from YouTube…',
            'Pulling each commenter\'s recent history…',
            'Running detection engine…',
            'Computing coordination signals…',
            'Building cross-links + synthesis…',
          ].map((p, i) => (
            <div key={i} className="flex items-center gap-2 font-mono text-2xs">
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${
                  i < phase ? 'bg-accent' : i === phase ? 'bg-accent animate-pulse' : 'bg-border-2'
                }`}
              />
              <span className={i <= phase ? 'text-fg-dim' : 'text-fg-mute'}>{p}</span>
            </div>
          ))}
        </div>
      )}

      {err && (
        <div className="flex items-start gap-2 p-3 bg-tier-high/10 border border-tier-high/30 rounded-sm">
          <AlertCircle size={14} className="text-tier-high mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-fg">{err}</p>
            {err.toLowerCase().includes("today") && (
              <Link
                href="/signup"
                className="inline-flex items-center gap-1 mt-2 font-mono text-2xs tracking-wider uppercase text-accent hover:underline"
              >
                Sign up to scan more <ArrowRight size={11} />
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DemoResult({
  result,
  onReset,
}: {
  result: ComprehensiveScanResult;
  onReset: () => void;
}) {
  const video = result.video;
  const tier = result.overall_tier || 'low';
  const cls = TIER_COLOR[tier] || TIER_COLOR.low;
  const icon = TIER_ICON[tier] || TIER_ICON.low;
  const coordPct = Math.round((video?.coordination_score || 0) * 100);
  const flagged = video?.commenters.filter(
    (c) => c.tier === 'elevated' || c.tier === 'high',
  ).length || 0;

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Hero reveal — score ring + verdict */}
      <div className="flex items-center gap-5 flex-wrap">
        <ScoreRing value={video?.coordination_score || 0} tier={tier} size={104} />
        <div className="flex-1 min-w-[200px] space-y-2">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2 py-1 rounded-sm border ${cls}`}
            >
              {icon}
              {tier} risk
            </span>
            <span className="font-mono text-2xs text-fg-mute">Scan complete</span>
          </div>
          <p className="text-sm text-fg leading-relaxed">{result.summary}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Commenters" value={video?.commenter_count || 0} icon={<Users size={11} />} />
        <Stat label="Flagged" value={flagged} icon={<ShieldAlert size={11} />} highlight={flagged > 0} />
        <Stat
          label="Coordination"
          value={`${coordPct}%`}
          icon={<Network size={11} />}
          highlight={coordPct >= 30}
        />
        <Stat label="Clusters" value={video?.clusters?.length || 0} highlight={(video?.clusters?.length || 0) > 0} />
      </div>

      {/* Top flagged commenters */}
      {video && video.commenters && (
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">
            Top commenters by suspicion
          </p>
          <div className="space-y-1.5">
            {[...video.commenters]
              .sort((a, b) => b.overall_probability - a.overall_probability)
              .slice(0, 5)
              .map((c) => (
                <div
                  key={c.external_id}
                  className="flex items-center gap-2 p-2 bg-bg rounded-sm border border-border-1"
                >
                  <span
                    className={`inline-flex items-center gap-1 font-mono text-2xs px-1.5 py-0.5 rounded-sm border ${
                      TIER_COLOR[c.tier] || TIER_COLOR.low
                    }`}
                  >
                    {TIER_ICON[c.tier]}
                    {c.tier}
                  </span>
                  <span className="text-sm text-fg truncate flex-1">{c.handle}</span>
                  <span className="font-mono text-2xs text-fg-mute tabular-nums">
                    {Math.round(c.overall_probability * 100)}%
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <div className="border-t border-border-1 pt-5 mt-5 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-sm text-fg-dim text-center sm:text-left">
          <span className="text-fg font-medium">Sign up</span> to save this scan, run more, and unlock evidence drilldown.
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="font-mono text-2xs tracking-wider uppercase px-3 py-2 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
          >
            ← Try another
          </button>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 bg-accent text-bg-deep font-medium px-4 py-2 rounded-sm hover:bg-accent-2 transition-colors"
          >
            Sign up free
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
  highlight,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div className="p-3 bg-bg rounded-sm border border-border-1">
      <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1">
        {icon}
        {label}
      </div>
      <div
        className={`font-mono text-lg font-semibold tabular-nums ${
          highlight ? 'text-tier-elevated' : 'text-fg'
        }`}
      >
        {value}
      </div>
    </div>
  );
}
