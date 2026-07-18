'use client';

import { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles } from 'lucide-react';
import { ApiError } from '@/lib/api';
import { runLinkScanJob, resumeLinkScanJob, ScanCancelledError, type LinkScanJob } from '@/lib/scan-job';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { ScanInput } from './scan-input';
import { LoadingOverlay } from './loading-overlay';

// AI-first investigation flow: the workspace only collects the input and runs the scan job. The
// deterministic engine works as the Evidence Compiler in the background; when the job completes the
// user is taken straight to the saved investigation page, whose ONLY results surface is the Omi
// Analyst (OpenRouter) assessment. No heuristic results are rendered here — if you see results,
// they came from the AI.

// A scan runs on the backend's pool and saves its investigation regardless of
// the UI. Persisting the in-flight job (per tab) lets the workspace re-attach
// after the user navigates away and back, so the redirect still happens instead
// of an empty page that reads as "cancelled".
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

interface State {
  pending: boolean;
  error: string | null;
}

export function Workspace({ initialUrl }: { initialUrl: string }) {
  const router = useRouter();
  const [batchSize, setBatchSize] = useState(25);
  const [state, setState] = useState<State>({ pending: false, error: null });
  // Real backend job state ('queued' | 'running' | …) so the progress overlay
  // reflects the actual scan, not a fabricated timeline.
  const [jobStatus, setJobStatus] = useState<LinkScanJob['status'] | null>(null);
  // Monotonic token: a newer scan supersedes any in-flight poll so a slow first
  // scan can't clobber the redirect of a second one the user kicked off.
  const activeRun = useRef(0);

  // Poll a (new or resumed) job to completion, then go straight to the saved
  // investigation — the AI-only results page. Shared by a fresh scan and by
  // re-attachment on mount. Nothing here holds an HTTP connection open for the
  // scan's duration, so it can't trip a proxy timeout.
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
      clearScan();
      router.push(`/investigations/${job.investigation_slug}`);
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
      setState({ pending: false, error: msg });
    }
  };

  const runScan = async (url: string) => {
    const runId = ++activeRun.current;
    setJobStatus('queued');
    setState({ pending: true, error: null });
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
  // restores the redirect instead of showing an empty (apparently cancelled) page.
  useEffect(() => {
    const saved = readScan();
    if (!saved || !saved.jobId) { if (saved) clearScan(); return; }
    if (Date.now() - (saved.ts || 0) > 9 * 60 * 1000) { clearScan(); return; } // stale
    const runId = ++activeRun.current;
    setJobStatus('running');
    setState({ pending: true, error: null });
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

  return (
    <div className="space-y-5 -mt-2">
      <header className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <span className="section-label">Intelligence · Workspace</span>
          <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-2">Investigate</h1>
        </div>
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
          Collecting evidence… when it&apos;s ready you&apos;ll be taken to the AI investigation.
          This scan keeps running if you leave the page — the result is saved to your Investigations.
        </p>
      )}

      {!state.pending && (
        <Card gradient className="relative overflow-hidden">
          <div className="relative flex gap-4">
            <div className="shrink-0 w-12 h-12 rounded-lg bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent">
              <Sparkles size={22} />
            </div>
            <div>
              <CardLabel>AI investigation</CardLabel>
              <CardTitle>Paste a YouTube or X (Twitter) link above to begin</CardTitle>
              <p className="text-sm text-fg-dim leading-relaxed max-w-xl">
                The Evidence Compiler collects the post, every commenter or replier, their recent
                histories, and cross-account coordination signals — then the Omi Analyst (AI)
                investigates the complete evidence and produces the assessment you&apos;ll see:
                the OMI score, verdict, evidence for and against, and a per-account reading.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
