'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertTriangle, Check, CheckSquare, ClipboardPaste, Layers, Loader2, Plus, Search, Square, Radar, ScanLine, X } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { ApiError, listCommenters, scoreSelection, type CommenterCandidate } from '@/lib/api';
import { resumeLinkScanJob, ScanCancelledError } from '@/lib/scan-job';

type Phase = 'idle' | 'compiling' | 'list' | 'scanning';

// A score job runs on the backend's pool and saves its investigation regardless of the UI.
// Persisting the in-flight job (per tab) lets this page re-attach after the user navigates
// away and back, so the redirect still happens instead of the scan looking cancelled.
const ACTIVE_SCAN_KEY = 'omi.investigate.activeScan';
type ActiveScan = { url: string; jobId: string; count: number; ts: number };

function persistScan(v: ActiveScan): void {
  try { sessionStorage.setItem(ACTIVE_SCAN_KEY, JSON.stringify(v)); } catch { /* ignore */ }
}
function clearScan(): void {
  try { sessionStorage.removeItem(ACTIVE_SCAN_KEY); } catch { /* ignore */ }
}
function readScan(): ActiveScan | null {
  try {
    const raw = sessionStorage.getItem(ACTIVE_SCAN_KEY);
    return raw ? (JSON.parse(raw) as ActiveScan) : null;
  } catch { return null; }
}

/**
 * Turn any failure into a clear, actionable line — a compile/scan must never look like it silently
 * "cut out". Maps every HTTP status the backend can return (and a dropped network) to plain English.
 */
function friendlyError(e: unknown, action: 'compile' | 'scan'): string {
  if (e instanceof ApiError) {
    switch (e.status) {
      case 400:
        return e.message || 'Paste a full YouTube video or X (Twitter) post link.';
      case 401:
        return 'Your session expired. Log in again, then retry.';
      case 402:
        return 'Out of credits. Visit Settings → Billing to top up.';
      case 403:
        return 'This account is not allowed to run scans. Contact support if that is unexpected.';
      case 404:
        return 'The scanning service is unavailable or still updating. Give it a minute, then try again.';
      case 429:
        return 'Too many requests right now. Wait a few seconds and try again.';
      case 502:
      case 503:
        // Backend sends a specific reason (missing key, provider down, private post) — surface it.
        return e.message || 'The scanning service is temporarily unavailable. Please try again shortly.';
      case 504:
        return 'The request took too long. It may still be working — try again in a moment.';
      default:
        return e.message || `Something went wrong (${e.status}). Please try again.`;
    }
  }
  // fetch() rejects with a TypeError when the network/API is unreachable.
  if (e instanceof TypeError) {
    return 'Could not reach the server. Check your connection and try again.';
  }
  if (e instanceof Error && e.message) return e.message;
  return action === 'compile'
    ? 'Could not read this post. Check the link and try again.'
    : 'The scan failed. Please try again.';
}

/**
 * Select-then-scan workspace. Paste a post → COMPILE the commenter list (free) → pick who to scan →
 * SCORE only the selection (paid). Blue compiles; purple runs the intelligence. The scanner-sweep +
 * staggered row reveal make the compile feel like an instrument reading the post, not a spinner.
 */
export function CommenterSelect({ initialUrl = '' }: { initialUrl?: string }) {
  const router = useRouter();
  const [url, setUrl] = useState(initialUrl);
  const [phase, setPhase] = useState<Phase>('idle');
  const [rows, setRows] = useState<CommenterCandidate[]>([]);
  const [platform, setPlatform] = useState<string>('');
  const [hasMore, setHasMore] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);          // add-more / compile in flight
  const [loadingAll, setLoadingAll] = useState(false); // "load all" pull in flight
  const [revealFrom, setRevealFrom] = useState(0);  // rows at/after this index animate in
  const [sweepKey, setSweepKey] = useState(0);      // retriggers the scanner sweep
  const [scanningCount, setScanningCount] = useState(0); // accounts in the in-flight score job
  const [query, setQuery] = useState('');           // filter the (potentially huge) list
  const runRef = useRef(0);

  // The list can hold the whole comment section, so browsing needs a filter (by handle or comment).
  const visibleRows = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) => (r.handle ?? r.external_id).toLowerCase().includes(q) || (r.comment ?? '').toLowerCase().includes(q),
    );
  }, [rows, query]);

  const selectableVisible = useMemo(() => visibleRows.filter((r) => !r.scanned), [visibleRows]);
  const allSelected = selectableVisible.length > 0 && selectableVisible.every((r) => selected.has(r.external_id));

  const compile = useCallback(async (opts: { fetch?: number; refresh?: boolean } = {}) => {
    if (!url.trim()) return;
    setError(null);
    // First load = a from-scratch compile (refresh, or no list yet). Only then do we swap to the
    // full compiling screen; "add more" on an existing list keeps the list up and shows inline busy.
    const firstLoad = opts.refresh || rows.length === 0;
    if (firstLoad) setPhase('compiling');
    setBusy(true);
    try {
      const prevTotal = opts.refresh ? 0 : rows.length;
      const res = await listCommenters(url.trim(), opts);
      setPlatform(res.platform);
      setRows(res.commenters);
      setHasMore(res.has_more);
      setRevealFrom(prevTotal);
      setSweepKey((k) => k + 1);
      setPhase('list');
    } catch (e) {
      setError(friendlyError(e, 'compile'));
      if (firstLoad) setPhase('idle');
    } finally {
      setBusy(false);
    }
  }, [url, rows.length]);

  // One-tap paste — reads the clipboard straight into the link field. Especially clean on mobile,
  // where pasting normally means long-press → menu → Paste. Silently no-ops if the browser blocks
  // clipboard reads (permissions / non-HTTPS) — the user can still paste by hand.
  const pasteFromClipboard = useCallback(async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setUrl(text.trim());
    } catch {
      /* clipboard unavailable — no-op */
    }
  }, []);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Select all / clear operates on what's currently visible (respects the filter), so picking
  // "everyone who mentioned X" is one action.
  const toggleAll = () =>
    setSelected((prev) => {
      if (allSelected) {
        const next = new Set(prev);
        for (const r of selectableVisible) next.delete(r.external_id);
        return next;
      }
      const next = new Set(prev);
      for (const r of selectableVisible) next.add(r.external_id);
      return next;
    });

  // Pull the WHOLE comment section, one bounded page at a time (each request stays fast, so a big
  // post can't time out a single call). Grows the same server-side cache until the pool is exhausted.
  const loadAll = useCallback(async () => {
    if (!url.trim() || loadingAll) return;
    setLoadingAll(true);
    setError(null);
    try {
      for (let guard = 0; guard < 40; guard++) {
        const res = await listCommenters(url.trim(), { fetch: 200 });
        setPlatform(res.platform);
        setRows(res.commenters);
        setHasMore(res.has_more);
        setRevealFrom(res.total); // bulk load — don't fire per-row reveals for hundreds of rows
        if (!res.has_more || res.fetched_now === 0) break;
      }
    } catch (e) {
      setError(friendlyError(e, 'compile'));
    } finally {
      setLoadingAll(false);
    }
  }, [url, loadingAll]);

  const rowsRef = useRef(0);
  rowsRef.current = rows.length;

  // Poll a (new or resumed) score job to completion, then go to the saved investigation.
  const pollToInvestigation = useCallback(async (jobId: string, runId: number, fallbackSlug: string | null) => {
    try {
      const done = await resumeLinkScanJob(jobId, () => runRef.current === runId, () => {});
      if (runRef.current !== runId) return;
      const slug = done.investigation_slug || fallbackSlug;
      if (done.status !== 'done' || !slug) {
        throw new Error(done.error || 'The scan finished but produced no investigation. Your credits were refunded — try again.');
      }
      clearScan();
      router.push(`/investigations/${slug}`);
    } catch (e) {
      if (e instanceof ScanCancelledError || runRef.current !== runId) return;
      clearScan();
      setError(friendlyError(e, 'scan'));
      setPhase((p) => (p === 'scanning' ? (rowsRef.current > 0 ? 'list' : 'idle') : p));
    }
  }, [router]);

  const scan = useCallback(async () => {
    const ids = [...selected];
    if (ids.length === 0) return;
    setError(null);
    setPhase('scanning');
    setScanningCount(ids.length);
    const runId = ++runRef.current;
    let job;
    try {
      job = await scoreSelection(url.trim(), ids);
    } catch (e) {
      if (runRef.current !== runId) return;
      setError(friendlyError(e, 'scan'));
      setPhase('list');
      return;
    }
    persistScan({ url: url.trim(), jobId: job.job_id, count: ids.length, ts: Date.now() });
    await pollToInvestigation(job.job_id, runId, job.investigation_slug);
  }, [selected, url, pollToInvestigation]);

  // On mount: re-attach to an in-flight score job the user navigated away from (the backend kept
  // running and saved its investigation, so resuming the poll restores the redirect). Otherwise,
  // arriving with a URL (e.g. "Scan more commenters" on an investigation) compiles immediately —
  // the list is cached server-side, so it comes back instantly and costs nothing.
  useEffect(() => {
    const saved = readScan();
    if (saved?.jobId && Date.now() - (saved.ts || 0) <= 9 * 60 * 1000) {
      const runId = ++runRef.current;
      setUrl(saved.url);
      setScanningCount(saved.count);
      setPhase('scanning');
      void pollToInvestigation(saved.jobId, runId, null);
      return;
    }
    if (saved) clearScan(); // stale or malformed
    if (initialUrl.trim()) void compile();
    // Mount-only: one re-attach or one auto-compile.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selCount = selected.size;

  return (
    <div className="space-y-5 -mt-2">
      <header className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <span className="section-label">Intelligence · Workspace</span>
          <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-2">Investigate</h1>
        </div>
        {platform && (
          <span className="font-mono text-2xs tracking-[0.16em] uppercase text-fg-mute">
            source · {platform === 'x' ? 'X / Twitter' : platform}
          </span>
        )}
      </header>

      {/* ── Input ─────────────────────────────────────────────────────────── */}
      <Card>
        <form
          onSubmit={(e) => { e.preventDefault(); void compile({ refresh: rows.length > 0 }); }}
          className="flex flex-col sm:flex-row gap-3"
        >
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="Paste a YouTube or X link…"
              aria-label="Post link"
              inputMode="url"
              autoCapitalize="off"
              autoCorrect="off"
              spellCheck={false}
              className="h-12 w-full pl-10 pr-14 sm:pr-24 text-base rounded-lg bg-bg-inset border border-border-2 text-fg
                         placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
            />
            {/* Auto-paste — one tap drops the copied link in. A big win on mobile, where pasting is fiddly. */}
            {!url.trim() ? (
              <button
                type="button"
                onClick={pasteFromClipboard}
                aria-label="Paste link from clipboard"
                className="btn-slab absolute right-1.5 top-1/2 -translate-y-1/2 h-9 px-2.5 sm:px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-accent-text"
              >
                {/* Icon-only on phones — the word costs ~45px that the placeholder needs to stay
                    readable, and the icon + aria-label already say what it does. */}
                <ClipboardPaste size={14} className="shrink-0" />
                <span className="hidden sm:inline">Paste</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setUrl('')}
                aria-label="Clear link"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fg-mute hover:text-fg p-1"
              >
                <X size={15} />
              </button>
            )}
          </div>
          {/* whitespace-nowrap: the label was breaking mid-phrase into "Compile" / "commenters" on a
              two-line button with the icon stranded on the left. shrink-0 on the icon keeps it from
              being squashed into an ellipse when the label is long. */}
          <button
            type="submit"
            disabled={!url.trim() || busy || phase === 'scanning'}
            className="btn-lamp h-12 w-full sm:w-auto px-6 rounded-lg font-semibold inline-flex items-center justify-center gap-2 whitespace-nowrap disabled:cursor-not-allowed"
          >
            {phase === 'compiling'
              ? <><Loader2 size={16} className="animate-spin shrink-0" /> Reading…</>
              : rows.length > 0
                ? <><ScanLine size={16} className="shrink-0" /> Re-read</>
                : <><ScanLine size={16} className="shrink-0" /> Compile commenters</>}
          </button>
        </form>
        <p className="mt-2.5 font-mono text-2xs tracking-wider text-fg-faint">
          Listing the commenters is free — no scoring, no credits. You choose who to scan next.
        </p>
      </Card>

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 flex items-start gap-2.5"
        >
          <AlertTriangle size={15} className="text-danger shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="font-mono text-2xs tracking-[0.16em] uppercase text-danger">Request failed</p>
            <p className="text-sm text-fg-dim leading-relaxed mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {phase === 'compiling' && <CompilingState />}

      {/* ── The commenter list ────────────────────────────────────────────── */}
      {phase === 'list' && rows.length > 0 && (
        <div className="rounded-xl border border-border-1 bg-bg-elev overflow-hidden">
          {/* HUD header */}
          <div className="px-4 py-3 border-b border-divider bg-bg/60 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="flex items-center gap-2 font-mono text-2xs tracking-[0.16em] uppercase text-accent-text">
                <Radar size={13} className="text-accent" />
                {query.trim() ? `${visibleRows.length} of ${rows.length}` : rows.length} commenter{rows.length === 1 ? '' : 's'}
                {query.trim() ? ' shown' : ' found'}
              </span>
              <span className="font-mono text-2xs tracking-[0.16em] uppercase text-violet-2">
                {selCount} selected
              </span>
              <div className="ml-auto flex items-center gap-2">
                <button
                  onClick={toggleAll}
                  disabled={selectableVisible.length === 0}
                  className="btn-slab h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim disabled:opacity-40"
                >
                  {allSelected ? <CheckSquare size={13} /> : <Square size={13} />}
                  {allSelected ? 'Clear' : query.trim() ? 'Select shown' : 'Select all'}
                </button>
                <button
                  onClick={() => void compile({ fetch: 100 })}
                  disabled={!hasMore || busy || loadingAll}
                  className="btn-slab h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim disabled:opacity-40"
                >
                  {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Add 100
                </button>
                <button
                  onClick={() => void loadAll()}
                  disabled={!hasMore || busy || loadingAll}
                  className="btn-slab h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-accent-text disabled:opacity-40"
                >
                  {loadingAll ? <Loader2 size={13} className="animate-spin" /> : <Layers size={13} />}
                  {loadingAll ? `Loading… ${rows.length}` : 'Load all'}
                </button>
              </div>
            </div>
            {/* Filter — a full comment section can be hundreds of rows; find a handle or phrase fast. */}
            {rows.length > 8 && (
              <div className="relative">
                <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by handle or comment…"
                  aria-label="Filter commenters"
                  className="h-9 w-full pl-8 pr-8 text-sm rounded-md bg-bg-inset border border-border-2 text-fg
                             placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
                />
                {query && (
                  <button
                    type="button"
                    onClick={() => setQuery('')}
                    aria-label="Clear filter"
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-mute hover:text-fg"
                  >
                    <X size={13} />
                  </button>
                )}
              </div>
            )}
          </div>

          {/* rows + the scanner sweep */}
          <div className="scan-shell relative max-h-[62vh] overflow-y-auto">
            <span key={sweepKey} className="scan-beam" aria-hidden />
            {visibleRows.length === 0 && (
              <p className="px-4 py-6 text-sm text-fg-mute text-center">No commenter matches “{query}”.</p>
            )}
            <ul>
              {visibleRows.map((r, i) => {
                const isSel = selected.has(r.external_id);
                // Only newly-compiled rows animate, and only the first ~40 of them (never a filtered
                // view) — a few hundred simultaneous entrances would stutter.
                const fresh = !query.trim() && i >= revealFrom && i - revealFrom < 40;
                return (
                  <li
                    key={r.external_id}
                    className={`commenter-row ${fresh ? 'reveal' : ''}`}
                    style={fresh ? ({ ['--i' as string]: Math.min(i - revealFrom, 18) }) : undefined}
                  >
                    <button
                      type="button"
                      disabled={r.scanned}
                      onClick={() => toggle(r.external_id)}
                      aria-pressed={isSel}
                      aria-label={`Select ${r.handle ?? r.external_id}${r.comment ? `, who commented: ${r.comment}` : ''}`}
                      className={`row-btn w-full text-left flex items-start gap-3 px-4 py-3.5 border-b border-divider
                        ${isSel ? 'is-selected' : ''} ${r.scanned ? 'is-scanned' : ''}`}
                    >
                      <Avatar src={r.avatar_url} handle={r.handle ?? r.external_id} />

                      <span className="min-w-0 flex-1">
                        {/* The comment is the hero — it's what you read to decide who to scan. */}
                        {r.comment ? (
                          <span className="comment-text block text-fg line-clamp-3">{r.comment}</span>
                        ) : (
                          <span className="block text-sm text-fg-mute italic">Engaged without a text comment</span>
                        )}
                        {/* Byline: who said it, kept quiet under the comment. */}
                        <span className="flex items-center gap-2 flex-wrap mt-1.5">
                          <span className="font-mono text-xs text-fg-mute truncate max-w-[16rem]">
                            @{(r.handle ?? r.external_id).replace(/^@/, '')}
                          </span>
                          {r.comment_count > 1 && (
                            <span className="font-mono text-[0.65rem] text-fg-faint">· {r.comment_count} comments</span>
                          )}
                          {r.scanned && (
                            <span className="font-mono text-[0.6rem] tracking-wider uppercase text-tier-low border border-tier-low/40 rounded px-1.5 py-0.5">
                              scanned
                            </span>
                          )}
                        </span>
                      </span>

                      {/* Selection pip — fills with a spring when picked. */}
                      {!r.scanned && (
                        <span className={`pip ${isSel ? 'pip-on' : ''}`} aria-hidden>
                          {isSel && <Check size={13} strokeWidth={3} />}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* action bar — on mobile the Scan button goes full-width + sticks to the bottom of the card */}
          <div className="flex items-center gap-3 flex-wrap px-4 py-3 border-t border-divider bg-bg/60 sticky bottom-0">
            <p className="font-mono text-2xs tracking-wider text-fg-faint w-full sm:w-auto">
              {hasMore ? 'More available — “Add 100” or “Load all” to pull the rest.' : 'Whole comment section loaded.'}
            </p>
            <button
              onClick={() => void scan()}
              disabled={selCount === 0}
              className="btn-ai w-full sm:w-auto sm:ml-auto h-11 px-5 rounded-lg font-semibold inline-flex items-center justify-center gap-2 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Radar size={15} />
              Scan {selCount > 0 ? `${selCount} ` : ''}selected
            </button>
          </div>
        </div>
      )}

      {/* Compile succeeded but the post has no listable commenters — say so instead of going blank. */}
      {phase === 'list' && rows.length === 0 && (
        <div className="rounded-xl border border-border-1 bg-bg-elev p-8 text-center">
          <span className="mx-auto mb-4 grid place-items-center w-11 h-11 rounded-full bg-bg-elev-2 border border-border-1">
            <Radar size={19} className="text-fg-mute" />
          </span>
          <p className="text-sm text-fg font-medium">No commenters found on this post</p>
          <p className="text-sm text-fg-mute mt-1 max-w-md mx-auto leading-relaxed">
            It may have comments turned off, no replies yet, or the link points to something without a
            public comment thread. Check the link and try again.
          </p>
          <button
            onClick={() => void compile({ refresh: true })}
            disabled={busy}
            className="btn-slab mt-4 h-9 px-4 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim disabled:opacity-40"
          >
            {busy ? <Loader2 size={13} className="animate-spin" /> : <ScanLine size={13} />} Re-read post
          </button>
        </div>
      )}

      {phase === 'scanning' && <ScanningState count={scanningCount} />}

      <style jsx>{`
        .scan-shell { scrollbar-width: thin; }
        .scan-beam {
          position: absolute; left: 0; right: 0; top: 0; height: 2px; z-index: 2; pointer-events: none;
          background: linear-gradient(90deg, transparent, var(--accent) 20%, var(--accent-2) 50%, var(--accent) 80%, transparent);
          box-shadow: 0 0 0 1px color-mix(in oklab, var(--accent) 30%, transparent);
          opacity: 0;
          animation: beam 720ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
        }
        /* Sweeps the visible list region (shell is max-h-[62vh]); vh keeps it on the GPU. */
        @keyframes beam {
          0% { transform: translateY(0); opacity: 0; }
          8% { opacity: 0.9; }
          92% { opacity: 0.9; }
          100% { transform: translateY(62vh); opacity: 0; }
        }
        /* content-visibility lets the browser skip rendering off-screen rows — the whole comment
           section (up to ~1000 rows) scrolls smoothly without a virtualization library. */
        .commenter-row { content-visibility: auto; contain-intrinsic-size: auto 76px; }
        .commenter-row.reveal {
          opacity: 0;
          animation: row-in 300ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
          animation-delay: calc(var(--i) * 32ms);
        }
        @keyframes row-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

        .row-btn { transition: background-color 140ms ease, box-shadow 140ms ease, transform 120ms ease-out; }
        /* Hover gated: touch taps fire a false :hover that would stick the tint on mobile. */
        @media (hover: hover) and (pointer: fine) {
          .row-btn:hover:not(:disabled) { background: var(--bg-elev-2); }
        }
        .row-btn:active:not(:disabled) { transform: scale(0.992); }
        .row-btn.is-selected {
          background: color-mix(in oklab, var(--violet-solid) 13%, var(--bg-elev));
          box-shadow: inset 3px 0 0 var(--violet-2);
        }
        .row-btn.is-scanned { opacity: 0.5; cursor: default; }

        /* The comment — the hero. Bigger and brighter than the byline, comfortable to read. */
        .comment-text { font-size: 0.95rem; line-height: 1.5; }

        /* Selection pip — the fun beat: an empty ring that fills with a spring when you pick someone. */
        .pip {
          margin-top: 2px; width: 22px; height: 22px; flex: none; border-radius: 999px;
          border: 1.5px solid var(--border-hot); display: grid; place-items: center; color: #fff;
          transition: background 120ms ease, border-color 120ms ease;
        }
        .pip-on { background: var(--violet-solid); border-color: var(--violet-solid); animation: pop 220ms cubic-bezier(0.34, 1.56, 0.64, 1); }
        @keyframes pop { 0% { transform: scale(0.7); } 60% { transform: scale(1.12); } 100% { transform: scale(1); } }

        @media (prefers-reduced-motion: reduce) {
          .scan-beam, .commenter-row.reveal, .pip-on { animation: none !important; }
          .commenter-row.reveal { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

// A commenter's avatar makes the list read like the real comment section. Small + subtle so the
// comment stays the hero; falls back to an initial monogram when there's no image (or it fails).
function Avatar({ src, handle }: { src?: string | null; handle: string }) {
  const [failed, setFailed] = useState(false);
  const initial = (handle || '?').replace(/^@/, '').charAt(0).toUpperCase() || '?';
  const base = 'w-9 h-9 mt-0.5 shrink-0 rounded-full';
  if (src && !failed) {
    // Native lazy-load + content-visibility means only on-screen avatars ever fetch. Plain <img>
    // (not next/image) because avatar hosts are arbitrary external CDNs we can't pre-allowlist.
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
        className={`${base} object-cover bg-bg-elev-2`}
      />
    );
  }
  return (
    <span
      className={`${base} grid place-items-center bg-bg-elev-2 border border-border-1 text-fg-mute font-mono text-sm font-semibold`}
      aria-hidden
    >
      {initial}
    </span>
  );
}

// The compile placeholder — a calm scanning indicator while the list is read.
function CompilingState() {
  return (
    <div className="rounded-xl border border-border-1 bg-bg-elev-2/50 p-8 flex items-center gap-4">
      <span className="relative grid place-items-center w-10 h-10 shrink-0">
        <Radar size={20} className="text-accent radar-spin" />
      </span>
      <div>
        <p className="text-sm text-fg">Reading the post…</p>
        <p className="text-xs text-fg-mute mt-0.5">Collecting the commenters and their comments. No scoring yet.</p>
      </div>
      <style jsx>{`
        .radar-spin { animation: spin 1.6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .radar-spin { animation: none; } }
      `}</style>
    </div>
  );
}

// The scan-in-progress state — the intelligence step is running on the selection.
function ScanningState({ count }: { count: number }) {
  return (
    <div className="rounded-xl border border-violet-solid/40 bg-violet-solid/[0.06] p-8">
      <div className="flex items-center gap-4">
        <span className="relative grid place-items-center w-12 h-12 shrink-0">
          <span className="ring" aria-hidden />
          <Radar size={22} className="text-violet-2 radar-spin" />
        </span>
        <div>
          <p className="text-sm text-fg font-medium">
            Analyzing {count} account{count === 1 ? '' : 's'}…
          </p>
          <p className="text-xs text-fg-mute mt-0.5">
            Pulling each account&apos;s history, detecting coordination, then Omi writes the verdict. This can take a
            couple of minutes — you&apos;ll be taken to the investigation when it&apos;s ready.
          </p>
        </div>
      </div>
      <style jsx>{`
        .radar-spin { animation: spin 1.6s linear infinite; }
        .ring {
          position: absolute; inset: 0; border-radius: 999px;
          border: 1.5px solid color-mix(in oklab, var(--violet-solid) 45%, transparent);
          border-top-color: var(--violet-2); animation: spin 1s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (prefers-reduced-motion: reduce) { .radar-spin, .ring { animation: none; } }
      `}</style>
    </div>
  );
}
