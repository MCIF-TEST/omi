'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Plus, Sparkles } from 'lucide-react';
import {
  apiClient,
  ApiError,
  type CommenterScanResult,
  type ComprehensiveScanResult,
  type InvestigationDetailResponse,
} from '@/lib/api';
import { runLinkScanJob, resumeLinkScanJob, ScanCancelledError, type LinkScanJob } from '@/lib/scan-job';

// A scan runs on the backend's pool and saves its investigation regardless of
// the UI. Persisting the in-flight job (per tab) lets the workspace re-attach
// after the user navigates away and back, so the result reappears instead of an
// empty page that reads as "cancelled".
const ACTIVE_SCAN_KEY = 'omi.investigate.activeScan';
type ActiveScan = { url: string; batchSize: number; jobId: string | null; ts: number };

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
import { Button } from '@/components/ui/button';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { ScanInput } from './scan-input';
import { CommenterList } from './commenter-list';
import { CommenterDetail } from './commenter-detail';
import { Synthesis } from './synthesis';
import { InsightsRail } from './insights-rail';
import { LoadingOverlay } from './loading-overlay';

interface State {
  data: ComprehensiveScanResult | null;
  selectedId: string | null;
  pending: boolean;
  error: string | null;
  loadingMore: boolean;
}

export function Workspace({ initialUrl }: { initialUrl: string }) {
  const router = useRouter();
  const [batchSize, setBatchSize] = useState(25);
  const [scanUrl, setScanUrl] = useState(initialUrl);
  const [state, setState] = useState<State>({
    data: null, selectedId: null, pending: false, error: null, loadingMore: false,
  });
  // Real backend job state ('queued' | 'running' | …) so the progress overlay
  // reflects the actual scan, not a fabricated timeline.
  const [jobStatus, setJobStatus] = useState<LinkScanJob['status'] | null>(null);
  // Monotonic token: a newer scan supersedes any in-flight poll so a slow first
  // scan can't clobber the result of a second one the user kicked off.
  const activeRun = useRef(0);

  // Poll a (new or resumed) job to completion, load the finished investigation,
  // and render it. Shared by a fresh scan and by re-attachment on mount. Nothing
  // here holds an HTTP connection open for the scan's duration, so it can't trip
  // a proxy timeout — the "reaches the last step then shows no result" failure.
  const completeRun = async (runId: number, jobPromise: Promise<LinkScanJob>) => {
    try {
      const job = await jobPromise;
      if (activeRun.current !== runId) return; // superseded
      if (job.status !== 'done' || !job.investigation_slug) {
        throw new Error(
          job.error ||
            'The scan finished but produced no result. Your credit was refunded — ' +
              'try again, or lower the batch size.',
        );
      }
      const detail = await apiClient<InvestigationDetailResponse>(
        `/v1/investigations/${job.investigation_slug}`,
      );
      if (activeRun.current !== runId) return;
      const data = detail.payload;
      if (!data || typeof data !== 'object' || !('overall_tier' in data)) {
        throw new Error('The scan finished but returned no result. Please try again.');
      }
      clearScan();
      setState({ data, selectedId: null, pending: false, error: null, loadingMore: false });
      router.refresh();   // refresh credits chip + recent investigations
    } catch (e) {
      if (e instanceof ScanCancelledError || activeRun.current !== runId) return;
      clearScan();
      const msg =
        e instanceof ApiError
          ? e.status === 401 ? 'Please log in to scan.'
          : e.status === 402 ? 'Out of credits. Visit Settings to subscribe.'
          : e.message
          : e instanceof Error && e.message
          ? e.message
          : 'Network error.';
      setState((s) => ({ ...s, pending: false, error: msg }));
    }
  };

  const runScan = async (url: string) => {
    const runId = ++activeRun.current;
    setScanUrl(url);
    setJobStatus('queued');
    setState((s) => ({ ...s, pending: true, error: null, data: null, selectedId: null }));
    persistScan({ url, batchSize, jobId: null, ts: Date.now() });
    await completeRun(
      runId,
      runLinkScanJob(
        { url, max_commenters: batchSize },
        () => activeRun.current === runId,
        (j) => {
          if (activeRun.current !== runId) return;
          setJobStatus(j.status);
          // Persist the job id once known so a navigation-interrupted scan can
          // be re-attached on return (it keeps running + saving server-side).
          if (j.job_id) persistScan({ url, batchSize, jobId: j.job_id, ts: Date.now() });
        },
      ),
    );
  };

  // On mount, re-attach to an in-flight scan the user navigated away from. The
  // backend job kept running and saved its investigation; resuming the poll
  // restores the result instead of showing an empty (apparently cancelled) page.
  useEffect(() => {
    const saved = readScan();
    if (!saved || !saved.jobId) { if (saved) clearScan(); return; }
    if (Date.now() - (saved.ts || 0) > 9 * 60 * 1000) { clearScan(); return; } // stale
    const runId = ++activeRun.current;
    setScanUrl(saved.url || '');
    setJobStatus('running');
    setState((s) => ({ ...s, pending: true, error: null }));
    void completeRun(
      runId,
      resumeLinkScanJob(
        saved.jobId,
        () => activeRun.current === runId,
        (j) => { if (activeRun.current === runId) setJobStatus(j.status); },
      ),
    );
    // Mount-only: re-attach a single in-flight scan if one exists.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadMore = async () => {
    const d = state.data;
    if (!d || !d.next_page_token || !d.investigation_slug) return;
    setState((s) => ({ ...s, loadingMore: true, error: null }));
    try {
      // Continuation batch via the same async job, keyed by the existing slug —
      // the worker merges (and deduplicates) the new commenters into the saved
      // investigation, so the reloaded payload is already the full list.
      const job = await runLinkScanJob({
        url: scanUrl,
        max_commenters: batchSize,
        start_page_token: d.next_page_token,
        investigation_slug: d.investigation_slug,
      });
      if (job.status !== 'done' || !job.investigation_slug) {
        throw new Error(job.error || 'Failed to load more.');
      }
      const detail = await apiClient<InvestigationDetailResponse>(
        `/v1/investigations/${job.investigation_slug}`,
      );
      setState((prev) => ({
        ...prev,
        loadingMore: false,
        // Preserve the running quota total the workspace has shown so far; the
        // reloaded payload only carries the latest batch's quota.
        data: prev.data
          ? { ...detail.payload, quota_used: (prev.data.quota_used || 0) + detail.payload.quota_used }
          : detail.payload,
      }));
      router.refresh();
    } catch (e) {
      if (e instanceof ScanCancelledError) return;
      setState((s) => ({
        ...s,
        loadingMore: false,
        error: e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Failed to load more.',
      }));
    }
  };

  const onSelect = (c: CommenterScanResult) =>
    setState((s) => ({ ...s, selectedId: c.external_id }));

  const selectedCommenter: CommenterScanResult | null =
    state.data?.video?.commenters.find((c) => c.external_id === state.selectedId) || null;
  const commenters = state.data?.video?.commenters || [];

  return (
    <div className="space-y-5 -mt-2">
      <header className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <span className="section-label">Intelligence · Workspace</span>
          <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-2">Investigate</h1>
        </div>
        {state.data?.investigation_slug && (
          <a
            href={`/investigations/${state.data.investigation_slug}`}
            className="font-mono text-2xs tracking-wider text-accent hover:text-accent-2 uppercase"
          >
            {state.data.investigation_slug} · permalink →
          </a>
        )}
      </header>

      <Card>
        <ScanInput
          initialUrl={initialUrl}
          pending={state.pending}
          batchSize={batchSize}
          onBatchSizeChange={setBatchSize}
          onScan={runScan}
        />
      </Card>

      {state.error && (
        <div className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger font-mono">
          {state.error}
        </div>
      )}

      <LoadingOverlay active={state.pending} status={jobStatus} />

      {state.pending && (
        <p className="text-center font-mono text-2xs tracking-wider uppercase text-fg-mute">
          This scan keeps running if you leave the page — the result is saved to your Investigations.
        </p>
      )}

      {state.data && (
        <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr_360px] gap-3 min-h-[640px]">
          {/* Left: commenter list */}
          <div className="flex flex-col rounded-2xl border border-border-1 bg-bg-elev overflow-hidden shadow-card">
            <div className="px-4 py-3 border-b border-border-1 bg-bg-elev-2/40 flex items-center justify-between gap-2 shrink-0">
              <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                Commenters
              </span>
              <span className="font-mono text-2xs text-accent-2 tabular-nums">
                {commenters.length}
              </span>
            </div>
            {commenters.length > 0 ? (
              <CommenterList
                commenters={commenters}
                selectedId={state.selectedId}
                onSelect={onSelect}
              />
            ) : (
              <div className="flex-1 flex items-center justify-center p-6 font-mono text-2xs text-fg-faint uppercase tracking-wider text-center">
                Channel-only scan — no commenter list.
              </div>
            )}
          </div>

          {/* Middle: synthesis / commenter detail */}
          <div className="flex flex-col rounded-2xl border border-border-1 bg-bg-elev overflow-hidden shadow-card min-w-0">
            <div className="px-4 py-3 border-b border-border-1 bg-bg-elev-2/40 flex items-center justify-between gap-2 shrink-0">
              <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                {selectedCommenter ? 'Commenter detail' : 'Synthesis'}
              </span>
              {selectedCommenter && (
                <button
                  onClick={() => setState(s => ({ ...s, selectedId: null }))}
                  className="font-mono text-2xs text-fg-mute hover:text-fg transition-colors tracking-wider uppercase"
                >
                  ← overview
                </button>
              )}
            </div>
            <div className="flex-1 overflow-y-auto">
              {selectedCommenter ? (
                <CommenterDetail
                  c={selectedCommenter}
                  investigationPlatform={state.data?.video?.platform}
                />
              ) : (
                <Synthesis data={state.data} />
              )}
            </div>
            {state.data.next_page_token && commenters.length > 0 && (
              <div className="border-t border-border-1 p-3 flex items-center justify-between gap-3 bg-bg-elev-2/30 shrink-0">
                <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
                  {commenters.length} loaded · more available
                </span>
                <Button onClick={loadMore} disabled={state.loadingMore} size="sm">
                  {state.loadingMore ? (
                    <><Loader2 size={12} className="animate-spin" /> Loading…</>
                  ) : (
                    <><Plus size={12} /> Scan next {batchSize}</>
                  )}
                </Button>
              </div>
            )}
          </div>

          {/* Right: insights rail */}
          <div className="flex flex-col rounded-2xl border border-border-1 bg-bg-elev overflow-hidden shadow-card">
            <div className="px-4 py-3 border-b border-border-1 bg-bg-elev-2/40 flex items-center justify-between gap-2 shrink-0">
              <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
                Cross-links
              </span>
              <span className="font-mono text-2xs text-accent-2 tabular-nums">
                {state.data.cross_links.length}
              </span>
            </div>
            <InsightsRail crossLinks={state.data.cross_links} />
          </div>
        </div>
      )}

      {!state.data && !state.pending && (
        <Card gradient className="relative overflow-hidden">
          <div className="relative flex gap-4">
            <div className="shrink-0 w-12 h-12 rounded-lg bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent">
              <Sparkles size={22} />
            </div>
            <div>
              <CardLabel>Empty workspace</CardLabel>
              <CardTitle>Paste a YouTube or X (Twitter) link above to begin</CardTitle>
              <p className="text-sm text-fg-dim leading-relaxed max-w-xl">
                Every comprehensive scan analyzes the post, every commenter or
                replier, their recent histories, and cross-account coordination
                signals — the same engine across platforms. Results are saved as
                an investigation you can return to later.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
