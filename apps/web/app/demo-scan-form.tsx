'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Loader2,
  AlertCircle,
  ArrowRight,
  ShieldAlert,
  Users,
  Network,
  Flame,
  Shield,
  AlertTriangle,
  Check,
  CheckSquare,
  Square,
  Radar,
  ScanLine,
} from 'lucide-react';
import {
  ApiError,
  demoListCommenters,
  demoScoreSelection,
  type CommenterCandidate,
  type ComprehensiveScanResult,
} from '@/lib/api';
import { ScoreRing } from '@/components/shared/score-ring';

const EXAMPLES = [
  'https://x.com/elonmusk/status/1790000000000000000',
  'https://x.com/nasa/status/1789000000000000000',
];

/** The free tier's ceiling, mirrored from the backend (DEMO_MAX_COMMENTERS). */
const FREE_MAX = 25;

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

type Phase = 'idle' | 'compiling' | 'list' | 'analyzing';

/** Any failure becomes one clear, actionable line — a free scan must never look like it silently
 *  cut out. Mirrors the workspace's friendlyError, minus the signed-in-only cases. */
function friendlyError(e: unknown, action: 'compile' | 'analyze'): string {
  if (e instanceof ApiError) {
    // 429 = the visitor's two free scans are spent; the backend's copy carries the CTA.
    if (e.status === 429 || e.status === 400) return e.message;
    if (e.status === 404) return 'That post could not be found. Check the link and try again.';
    if (e.status === 502 || e.status === 503) {
      return e.message || 'The scanning service is busy right now. Please try again in a moment.';
    }
    if (e.status === 504) return 'That took too long. Try again with a smaller selection.';
    return e.message || `Something went wrong (${e.status}). Please try again.`;
  }
  if (e instanceof TypeError) return 'Could not reach the server. Check your connection and try again.';
  if (e instanceof Error && e.message) return e.message;
  return action === 'compile'
    ? 'Could not read that post. Check the link and try again.'
    : 'The analysis failed. Please try again.';
}

/**
 * The free pre-login scan — the same three moves as the signed-in workspace: paste an X post,
 * COMPILE its repliers (free, no analysis), pick who to check, then ANALYZE only that selection with
 * the real engine. Blue compiles; purple runs the intelligence.
 */
export function DemoScanForm() {
  const [url, setUrl] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [rows, setRows] = useState<CommenterCandidate[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<ComprehensiveScanResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [limitReached, setLimitReached] = useState(false);

  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.external_id));

  const compile = useCallback(async () => {
    if (!url.trim()) return;
    setErr(null);
    setResult(null);
    setSelected(new Set());
    setPhase('compiling');
    try {
      const res = await demoListCommenters(url.trim());
      setRows(res.commenters);
      // Pre-select everything: the fastest path to a verdict is one click, and the free tier is
      // already capped at 25 — deselecting is the rarer intent.
      setSelected(new Set(res.commenters.map((c) => c.external_id)));
      setPhase('list');
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) setLimitReached(true);
      setErr(friendlyError(e, 'compile'));
      setPhase('idle');
    }
  }, [url]);

  const analyze = useCallback(async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    setErr(null);
    setPhase('analyzing');
    try {
      const body = await demoScoreSelection(url.trim(), ids);
      setResult(body);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) setLimitReached(true);
      setErr(friendlyError(e, 'analyze'));
      setPhase('list');
    }
  }, [selected, url]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const toggleAll = () =>
    setSelected((prev) => (allSelected ? new Set() : new Set(rows.map((r) => r.external_id))));

  const reset = () => {
    setResult(null);
    setRows([]);
    setSelected(new Set());
    setUrl('');
    setErr(null);
    setPhase('idle');
  };

  if (result) return <DemoResult result={result} onReset={reset} />;

  const selCount = selected.size;

  return (
    <div className="space-y-4">
      {/* ── Step 1 · paste + compile ─────────────────────────────────────── */}
      <form
        onSubmit={(e) => { e.preventDefault(); void compile(); }}
        className="flex gap-2 flex-wrap"
      >
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://x.com/…/status/…"
          disabled={phase === 'compiling' || phase === 'analyzing' || limitReached}
          required
          inputMode="url"
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          className="flex-1 min-w-[280px] px-4 py-3 bg-bg border border-border-1 rounded-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!url.trim() || phase === 'compiling' || phase === 'analyzing' || limitReached}
          className="inline-flex items-center gap-2 btn-lamp font-semibold px-5 py-3 rounded-md disabled:cursor-not-allowed"
        >
          {phase === 'compiling'
            ? <><Loader2 size={16} className="animate-spin" /> Reading…</>
            : <><ScanLine size={16} /> {rows.length > 0 ? 'Re-read post' : 'Compile repliers'}</>}
        </button>
      </form>

      {phase === 'idle' && !err && (
        <div className="flex items-center gap-2 flex-wrap font-mono text-2xs text-fg-mute">
          <span>Try:</span>
          {EXAMPLES.map((u) => (
            <button
              key={u}
              type="button"
              onClick={() => setUrl(u)}
              className="text-accent hover:underline truncate max-w-[280px]"
            >
              {u.replace('https://', '')}
            </button>
          ))}
          <span className="text-fg-mute/70">
            · listing repliers is free · up to {FREE_MAX} · 2 free analyses per visitor
          </span>
        </div>
      )}

      {phase === 'compiling' && (
        <div className="flex items-center gap-3 p-4 rounded-sm border border-border-1 bg-bg">
          <Radar size={18} className="text-accent radar-spin" />
          <div>
            <p className="text-sm text-fg">Reading the post…</p>
            <p className="text-xs text-fg-mute mt-0.5">
              Collecting who replied and what they said. No analysis yet.
            </p>
          </div>
        </div>
      )}

      {/* ── Step 2 · pick who to analyze ─────────────────────────────────── */}
      {phase === 'list' && rows.length > 0 && (
        <div className="rounded-lg border border-border-1 bg-bg overflow-hidden">
          <div className="px-4 py-2.5 border-b border-border-1 flex items-center gap-3 flex-wrap">
            <span className="font-mono text-2xs tracking-[0.16em] uppercase text-accent">
              {rows.length} replier{rows.length === 1 ? '' : 's'} found
            </span>
            <span className="font-mono text-2xs tracking-[0.16em] uppercase text-violet-2">
              {selCount} selected
            </span>
            <button
              type="button"
              onClick={toggleAll}
              className="ml-auto inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
            >
              {allSelected ? <CheckSquare size={12} /> : <Square size={12} />}
              {allSelected ? 'Clear' : 'Select all'}
            </button>
          </div>

          <ul className="max-h-[42vh] overflow-y-auto">
            {rows.map((r, i) => {
              const isSel = selected.has(r.external_id);
              return (
                <li
                  key={r.external_id}
                  className="demo-row"
                  style={i < 20 ? ({ ['--i' as string]: i }) : undefined}
                >
                  <button
                    type="button"
                    onClick={() => toggle(r.external_id)}
                    aria-pressed={isSel}
                    aria-label={`Select ${r.handle ?? r.external_id}`}
                    className={`row-btn w-full text-left flex items-start gap-3 px-4 py-3 border-b border-border-1 ${
                      isSel ? 'is-selected' : ''
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      {r.comment ? (
                        <span className="block text-sm text-fg leading-snug line-clamp-2">{r.comment}</span>
                      ) : (
                        <span className="block text-sm text-fg-mute italic">Replied without text</span>
                      )}
                      <span className="block font-mono text-2xs text-fg-mute mt-1 truncate">
                        @{(r.handle ?? r.external_id).replace(/^@/, '')}
                      </span>
                    </span>
                    <span className={`pip ${isSel ? 'pip-on' : ''}`} aria-hidden>
                      {isSel && <Check size={12} strokeWidth={3} />}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="flex items-center gap-3 flex-wrap px-4 py-3 border-t border-border-1">
            <p className="font-mono text-2xs tracking-wider text-fg-faint">
              Free scan · up to {FREE_MAX} repliers
            </p>
            <button
              type="button"
              onClick={() => void analyze()}
              disabled={selCount === 0}
              className="ml-auto inline-flex items-center gap-2 btn-ai font-semibold px-5 py-2.5 rounded-md disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Radar size={15} />
              Analyze {selCount > 0 ? `${selCount} ` : ''}selected
            </button>
          </div>
        </div>
      )}

      {/* Compiled fine, but nobody replied. */}
      {phase === 'list' && rows.length === 0 && (
        <div className="rounded-sm border border-border-1 bg-bg p-6 text-center">
          <p className="text-sm text-fg">No repliers on this post</p>
          <p className="text-sm text-fg-mute mt-1">
            It may have no replies yet, or replies may be restricted. Try another post.
          </p>
        </div>
      )}

      {/* ── Step 3 · the real analysis ───────────────────────────────────── */}
      {phase === 'analyzing' && (
        <div className="rounded-lg border border-violet-solid/40 bg-violet-solid/[0.06] p-5 flex items-center gap-4">
          <Radar size={20} className="text-violet-2 radar-spin shrink-0" />
          <div>
            <p className="text-sm text-fg font-medium">
              Analyzing {selCount} account{selCount === 1 ? '' : 's'}…
            </p>
            <p className="text-xs text-fg-mute mt-0.5 leading-relaxed">
              Pulling each account&apos;s history, detecting coordination, then Omi writes the verdict.
              This takes up to a minute.
            </p>
          </div>
        </div>
      )}

      {err && (
        <div className="flex items-start gap-2 p-3 bg-tier-high/10 border border-tier-high/30 rounded-sm">
          <AlertCircle size={14} className="text-tier-high mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-fg">{err}</p>
            {limitReached && (
              <Link
                href="/sign-up"
                className="inline-flex items-center gap-1 mt-2 font-mono text-2xs tracking-wider uppercase text-accent hover:underline"
              >
                Create a free account <ArrowRight size={11} />
              </Link>
            )}
          </div>
        </div>
      )}

      <style jsx>{`
        .radar-spin { animation: spin 1.6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }

        .demo-row { opacity: 0; animation: row-in 280ms cubic-bezier(0.23, 1, 0.32, 1) forwards; }
        .demo-row:not([style]) { opacity: 1; animation: none; }
        .demo-row[style] { animation-delay: calc(var(--i) * 28ms); }
        @keyframes row-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

        .row-btn { transition: background-color 140ms ease, transform 120ms ease-out; }
        @media (hover: hover) and (pointer: fine) {
          .row-btn:hover { background: var(--bg-elev); }
        }
        .row-btn:active { transform: scale(0.994); }
        .row-btn.is-selected {
          background: color-mix(in oklab, var(--violet-solid) 12%, transparent);
          box-shadow: inset 3px 0 0 var(--violet-2);
        }

        .pip {
          margin-top: 1px; width: 20px; height: 20px; flex: none; border-radius: 999px;
          border: 1.5px solid var(--border-hot); display: grid; place-items: center; color: #fff;
          transition: background 120ms ease, border-color 120ms ease;
        }
        .pip-on {
          background: var(--violet-solid); border-color: var(--violet-solid);
          animation: pop 200ms cubic-bezier(0.34, 1.56, 0.64, 1);
        }
        @keyframes pop { 0% { transform: scale(0.8); } 60% { transform: scale(1.1); } 100% { transform: scale(1); } }

        @media (prefers-reduced-motion: reduce) {
          .radar-spin, .demo-row, .pip-on { animation: none !important; }
          .demo-row { opacity: 1; }
        }
      `}</style>
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
  const flagged = useMemo(
    () => video?.commenters.filter((c) => c.tier === 'elevated' || c.tier === 'high').length || 0,
    [video],
  );

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
            <span className="font-mono text-2xs text-fg-mute">Analysis complete</span>
          </div>
          <p className="text-sm text-fg leading-relaxed">{result.summary}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Analyzed" value={video?.commenter_count || 0} icon={<Users size={11} />} />
        <Stat label="Flagged" value={flagged} icon={<ShieldAlert size={11} />} highlight={flagged > 0} />
        <Stat
          label="Coordination"
          value={`${coordPct}%`}
          icon={<Network size={11} />}
          highlight={coordPct >= 30}
        />
        <Stat label="Clusters" value={video?.clusters?.length || 0} highlight={(video?.clusters?.length || 0) > 0} />
      </div>

      {/* Per-account read — the whole point of the product */}
      {video && video.commenters && (
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-2">
            Top repliers by suspicion
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
          <span className="text-fg font-medium">Sign up</span> to save this scan, analyze whole comment
          sections, and open the evidence behind every score.
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onReset}
            className="font-mono text-2xs tracking-wider uppercase px-3 py-2 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
          >
            ← Scan another
          </button>
          <Link
            href="/sign-up"
            className="inline-flex items-center gap-2 btn-lamp font-semibold px-4 py-2 rounded-md"
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
