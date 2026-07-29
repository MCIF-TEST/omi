'use client';

import { useCallback, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Loader2,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ShieldAlert,
  Users,
  Network,
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
  type Tier,
} from '@/lib/api';
import { ScoreRing } from '@/components/shared/score-ring';
import { TierBadge } from '@/components/shared/tier-badge';

/** The free tier's ceiling, mirrored from the backend (DEMO_MAX_COMMENTERS). */
const FREE_MAX = 25;

type Phase = 'idle' | 'compiling' | 'list' | 'analyzing';

/** Any failure becomes one clear, actionable line, because a free scan must never look like it
 *  silently cut out. Mirrors the workspace's friendlyError, minus the signed-in-only cases. */
function friendlyError(e: unknown, action: 'compile' | 'analyze'): string {
  if (e instanceof ApiError) {
    // 429 = the visitor's free scan is spent; the backend's copy carries the CTA.
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
 * The free pre-login scan. Same three moves as the signed-in workspace: paste an X post,
 * COMPILE its repliers (free, no analysis), pick who to check, then ANALYZE only that selection
 * with the real engine. Blue compiles; purple runs the intelligence.
 *
 * Styling tracks `app/(app)/investigate/commenter-select.tsx` deliberately: same input material
 * (h-12 sunk well on a hairline), same HUD header, same selection pip, same action-bar anatomy.
 * A visitor who scans here should find the signed-in workspace already familiar.
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
      // already capped at 25, so deselecting is the rarer intent.
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
  const locked = phase === 'compiling' || phase === 'analyzing' || limitReached;

  return (
    <div className="space-y-4">
      {/* ── Step 1 · paste + compile ─────────────────────────────────────── */}
      <form
        onSubmit={(e) => { e.preventDefault(); void compile(); }}
        className="flex flex-col sm:flex-row gap-3"
      >
        <div className="relative flex-1">
          <ScanLine
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none"
            aria-hidden
          />
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="Paste an X post link…"
            aria-label="X post link"
            disabled={locked}
            required
            inputMode="url"
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            className="h-12 w-full pl-10 pr-3 text-base rounded-lg bg-bg-inset border border-border-2 text-fg
                       placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent
                       focus-visible:outline disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={!url.trim() || locked}
          className="btn-lamp h-12 w-full sm:w-auto px-6 rounded-lg font-semibold inline-flex items-center
                     justify-center gap-2 whitespace-nowrap disabled:cursor-not-allowed"
        >
          {phase === 'compiling'
            ? <><Loader2 size={16} className="animate-spin shrink-0" /> Reading…</>
            : <><ScanLine size={16} className="shrink-0" /> {rows.length > 0 ? 'Re-read post' : 'Compile repliers'}</>}
        </button>
      </form>

      {/* A format hint, not clickable examples. The two sample links that used to sit here carried
          invented status ids, so the first thing a curious visitor clicked filled the field with a
          post that cannot resolve and answered them with an error. */}
      {phase === 'idle' && !err && (
        <div className="flex items-center gap-x-2 gap-y-1 flex-wrap font-mono text-2xs text-fg-mute tracking-wider">
          <span className="text-fg-dim">x.com/&lt;account&gt;/status/&lt;id&gt;</span>
          <span className="text-fg-faint">
            · listing repliers is free · up to {FREE_MAX} · 2 free analyses per visitor
          </span>
        </div>
      )}

      {phase === 'compiling' && (
        <div className="rounded-xl border border-border-1 bg-bg-elev-2/50 p-5 flex items-center gap-4">
          <Radar size={20} className="text-accent radar-spin shrink-0" aria-hidden />
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
        <div className="rounded-xl border border-border-1 bg-bg-elev overflow-hidden">
          {/* HUD header: same anatomy as the signed-in workspace */}
          <div className="px-4 py-3 border-b border-divider bg-bg/60 flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-2 font-mono text-2xs tracking-[0.16em] uppercase text-accent-text">
              <Radar size={13} className="text-accent" aria-hidden />
              {rows.length} replier{rows.length === 1 ? '' : 's'} found
            </span>
            <span className="font-mono text-2xs tracking-[0.16em] uppercase text-violet-2">
              {selCount} selected
            </span>
            <button
              type="button"
              onClick={toggleAll}
              className="btn-slab ml-auto h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim"
            >
              {allSelected ? <CheckSquare size={13} /> : <Square size={13} />}
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
                    className={`row-btn w-full text-left flex items-start gap-3 px-4 py-3.5 border-b border-divider ${
                      isSel ? 'is-selected' : ''
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      {r.comment ? (
                        <span className="comment-text block text-fg line-clamp-2">{r.comment}</span>
                      ) : (
                        <span className="block text-sm text-fg-mute italic">Replied without text</span>
                      )}
                      <span className="block font-mono text-xs text-fg-mute mt-1.5 truncate">
                        @{(r.handle ?? r.external_id).replace(/^@/, '')}
                      </span>
                    </span>
                    <span className={`pip ${isSel ? 'pip-on' : ''}`} aria-hidden>
                      {isSel && <Check size={13} strokeWidth={3} />}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="flex items-center gap-3 flex-wrap px-4 py-3 border-t border-divider bg-bg/60">
            <p className="font-mono text-2xs tracking-wider text-fg-faint w-full sm:w-auto">
              Free scan · up to {FREE_MAX} repliers
            </p>
            <button
              type="button"
              onClick={() => void analyze()}
              disabled={selCount === 0}
              className="btn-ai w-full sm:w-auto sm:ml-auto h-11 px-5 rounded-lg font-semibold inline-flex
                         items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Radar size={15} />
              Analyze {selCount > 0 ? `${selCount} ` : ''}selected
            </button>
          </div>
        </div>
      )}

      {/* Compiled fine, but nobody replied. */}
      {phase === 'list' && rows.length === 0 && (
        <div className="rounded-xl border border-border-1 bg-bg-elev p-8 text-center">
          <span className="mx-auto mb-4 grid place-items-center w-11 h-11 rounded-full bg-bg-elev-2 border border-border-1">
            <Radar size={19} className="text-fg-mute" aria-hidden />
          </span>
          <p className="text-sm text-fg font-medium">No repliers on this post</p>
          <p className="text-sm text-fg-mute mt-1 max-w-md mx-auto leading-relaxed">
            It may have no replies yet, or replies may be restricted. Try another post.
          </p>
        </div>
      )}

      {/* ── Step 3 · the real analysis ───────────────────────────────────── */}
      {phase === 'analyzing' && (
        <div className="rounded-xl border border-violet-solid/40 bg-violet-solid/[0.06] p-5 flex items-center gap-4">
          <Radar size={20} className="text-violet-2 radar-spin shrink-0" aria-hidden />
          <div>
            <p className="text-sm text-fg font-medium">
              Analyzing {selCount} account{selCount === 1 ? '' : 's'}…
            </p>
            <p className="text-xs text-fg-mute mt-0.5 leading-relaxed">
              Pulling each account&apos;s history, detecting coordination, then Omi writes the verdict.
              This is the real analysis, so it can take a couple of minutes. Keep this tab open.
            </p>
          </div>
        </div>
      )}

      {err && (
        <div
          role="alert"
          className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 flex items-start gap-2.5"
        >
          <AlertTriangle size={15} className="text-danger shrink-0 mt-0.5" aria-hidden />
          <div className="min-w-0">
            <p className="font-mono text-2xs tracking-[0.16em] uppercase text-danger">Request failed</p>
            <p className="text-sm text-fg-dim leading-relaxed mt-0.5">{err}</p>
            {limitReached && (
              <Link
                href="/sign-up"
                className="inline-flex items-center gap-1 mt-2 font-mono text-2xs tracking-wider uppercase text-accent-text hover:underline"
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

        .row-btn { transition: background-color 140ms ease, box-shadow 140ms ease, transform 120ms ease-out; }
        /* Hover gated: touch taps fire a false :hover that would stick the tint on mobile. */
        @media (hover: hover) and (pointer: fine) {
          .row-btn:hover { background: var(--bg-elev-2); }
        }
        .row-btn:active { transform: scale(0.994); }
        .row-btn.is-selected {
          background: color-mix(in oklab, var(--violet-solid) 13%, var(--bg-elev));
          box-shadow: inset 3px 0 0 var(--violet-2);
        }

        /* The comment is the hero: bigger than the byline, comfortable to read. */
        .comment-text { font-size: 0.95rem; line-height: 1.5; }

        .pip {
          margin-top: 2px; width: 22px; height: 22px; flex: none; border-radius: 999px;
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
  const tier = (result.overall_tier || 'low') as Tier;
  const coordPct = Math.round((video?.coordination_score || 0) * 100);
  const flagged = useMemo(
    () => video?.commenters.filter((c) => c.tier === 'elevated' || c.tier === 'high').length || 0,
    [video],
  );

  return (
    <div className="space-y-5 animate-fade-up">
      {/* Verdict hero: the score ring fused with the tier and the written summary */}
      <div className="flex items-center gap-5 flex-wrap">
        <ScoreRing value={video?.coordination_score || 0} tier={tier} size={104} />
        <div className="flex-1 min-w-[200px] space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <TierBadge tier={tier} size="md" />
            <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
              Analysis complete
            </span>
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

      {/* The analyst's reading: the same model output a signed-in investigation gets. Absent when
          the analyst is off or its call failed; the scored accounts below stand on their own. */}
      {result.analyst_assessment && (
        <div className="rounded-xl border border-violet-solid/30 bg-violet-solid/[0.05] p-4">
          <p className="font-mono text-2xs tracking-[0.18em] uppercase text-violet-2 mb-2">
            Omi Analyst
          </p>
          {result.analyst_assessment.headline && (
            <p className="text-sm text-fg font-medium leading-snug mb-1.5">
              {result.analyst_assessment.headline}
            </p>
          )}
          {result.analyst_assessment.assessment && (
            <p className="text-sm text-fg-dim leading-relaxed">
              {result.analyst_assessment.assessment}
            </p>
          )}
        </div>
      )}

      {/* Per-account read: the whole point of the product */}
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
                  className="flex items-center gap-2.5 p-2.5 bg-bg-inset rounded-lg border border-border-1"
                >
                  <TierBadge tier={c.tier as Tier} size="sm" />
                  <span className="text-sm text-fg truncate flex-1">{c.handle}</span>
                  <span className="font-mono text-2xs text-fg-mute tabular">
                    {Math.round(c.overall_probability * 100)}%
                  </span>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* CTA */}
      <div className="border-t border-divider pt-5 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-sm text-fg-dim text-center sm:text-left">
          <span className="text-fg font-medium">Sign up</span> to save this scan, analyze whole comment
          sections, and open the evidence behind every score.
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={onReset}
            className="btn-slab h-9 px-3 rounded-md font-mono text-2xs tracking-wider uppercase text-fg-dim inline-flex items-center gap-1.5"
          >
            <ArrowLeft size={12} />
            Scan another
          </button>
          <Link
            href="/sign-up"
            className="btn-lamp h-9 px-4 rounded-md font-semibold text-sm inline-flex items-center gap-2"
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
    <div className="p-3.5 bg-bg-elev-2 rounded-xl border border-border-1 surface-lit">
      <div className="flex items-center gap-1.5 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1.5">
        {icon}
        {label}
      </div>
      <div className={`stat-value text-lg ${highlight ? 'text-tier-elevated' : 'text-fg'}`}>
        {value}
      </div>
    </div>
  );
}
