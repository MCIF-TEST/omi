'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import { Zap, CheckCircle, XCircle, Clock, ArrowRight, Loader2 } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { Button } from '@/components/ui/button';
import { apiClient, type BulkScanJobResponse, type BulkScanJobResult, type BulkScanJobSummary } from '@/lib/api';
import { timeAgo } from '@/lib/format';

type Step = 'input' | 'running' | 'done';

export function BulkClient({ credits }: { credits: number }) {
  const [step, setStep] = useState<Step>('input');
  const [urlText, setUrlText] = useState('');
  const [maxCommenters, setMaxCommenters] = useState(100);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<BulkScanJobSummary | null>(null);
  const [results, setResults] = useState<BulkScanJobResult[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const urls = urlText
    .split('\n')
    .map((u) => u.trim())
    .filter(Boolean);
  const urlCount = Math.min(urls.length, 20);
  const creditsNeeded = urlCount;
  const canAfford = credits >= creditsNeeded;

  const stopPoll = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const res = await apiClient<BulkScanJobResponse>(`/v1/scan/bulk/${jobId}`);
      setJob(res.job);
      setResults(res.results);
      if (res.job.status === 'done' || res.job.status === 'failed') {
        stopPoll();
        setStep('done');
      }
    } catch { /* keep polling */ }
  }, [stopPoll]);

  const submit = async () => {
    if (!urlCount || !canAfford) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await apiClient<BulkScanJobResponse>('/v1/scan/bulk', {
        method: 'POST',
        body: JSON.stringify({ urls: urls.slice(0, 20), max_commenters: maxCommenters }),
      });
      setJob(res.job);
      setResults(res.results);
      setStep('running');
      // Poll every 4 seconds until done
      pollRef.current = setInterval(() => pollJob(res.job.job_id), 4000);
    } catch (e: any) {
      setError(e.message || 'Failed to start job');
    } finally {
      setSubmitting(false);
    }
  };

  // Cleanup on unmount
  useEffect(() => () => stopPoll(), [stopPoll]);

  if (step === 'input') {
    return (
      <div className="space-y-6 max-w-2xl">
        <div>
          <label className="font-mono text-2xs tracking-wider uppercase text-fg-mute block mb-2">
            URLs to scan (one per line, max 20)
          </label>
          <textarea
            aria-label="YouTube URLs to scan, one per line"
            value={urlText}
            onChange={(e) => setUrlText(e.target.value)}
            placeholder={`https://youtube.com/watch?v=abc123\nhttps://youtube.com/watch?v=xyz789\nhttps://youtube.com/@ChannelName`}
            rows={10}
            className="w-full px-4 py-3 bg-bg-elev border border-border-2 rounded-md text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent font-mono resize-y"
          />
          {urlText && urls.length > 20 && (
            <p className="text-xs text-amber-400 mt-1">
              Only the first 20 URLs will be scanned.
            </p>
          )}
        </div>

        <div>
          <label className="font-mono text-2xs tracking-wider uppercase text-fg-mute block mb-2">
            Max commenters per video
          </label>
          <div className="flex items-center gap-3">
            <input
              aria-label="Max commenters per scan"
              type="range"
              min={5} max={300} step={5}
              value={maxCommenters}
              onChange={(e) => setMaxCommenters(Number(e.target.value))}
              className="flex-1 accent-accent"
            />
            <span className="font-mono text-sm text-fg w-12 text-right">{maxCommenters}</span>
          </div>
          <p className="text-xs text-fg-mute mt-1">
            Higher = more accurate but slower + uses more YouTube quota.
          </p>
        </div>

        {urlCount > 0 && (
          <div className="bg-bg-elev border border-border-1 rounded-sm px-4 py-3 flex items-center gap-4 text-sm">
            <div className="flex-1 space-y-0.5">
              <div className="font-mono text-xs text-fg">
                <span className="text-fg-dim">{urlCount} URL{urlCount === 1 ? '' : 's'} · </span>
                <span className={creditsNeeded > credits ? 'text-danger' : 'text-accent'}>
                  {creditsNeeded} credit{creditsNeeded === 1 ? '' : 's'}
                </span>
                <span className="text-fg-mute"> (you have {credits})</span>
              </div>
              {!canAfford && (
                <p className="text-xs text-danger">Not enough credits.</p>
              )}
            </div>
          </div>
        )}

        {error && (
          <p className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-sm px-4 py-3">
            {error}
          </p>
        )}

        <Button
          onClick={submit}
          disabled={!urlCount || !canAfford || submitting}
          size="lg"
        >
          {submitting ? (
            <><Loader2 size={14} className="animate-spin" /> Starting job…</>
          ) : (
            <><Zap size={14} /> Start bulk scan</>
          )}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* Progress header */}
      {job && (
        <div className="bg-bg-elev border border-border-1 rounded-md p-5 space-y-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1">
                Bulk job · {job.job_id}
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={job.status} />
                <span className="text-sm text-fg-dim font-mono">
                  {job.completed}/{job.total} scanned
                  {job.failed_count > 0 && ` · ${job.failed_count} failed`}
                </span>
              </div>
            </div>
            {step === 'running' && (
              <Loader2 size={20} className="text-accent animate-spin" />
            )}
          </div>

          {/* Progress bar */}
          <div>
            <div className="h-2 bg-border-1 rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-500"
                style={{ width: `${job.total ? (job.completed / job.total) * 100 : 0}%` }}
              />
            </div>
            <div className="flex justify-between mt-1 font-mono text-2xs text-fg-mute">
              <span>{job.credits_used} credits used</span>
              {job.completed_at ? (
                <span>Done {timeAgo(job.completed_at)}</span>
              ) : (
                <span>~{(job.total - job.completed) * 30}s remaining</span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Results list */}
      <div className="space-y-2">
        {results.map((r, i) => (
          <ResultRow key={i} result={r} />
        ))}
      </div>

      {step === 'done' && (
        <div className="flex gap-3">
          <Button
            variant="secondary"
            onClick={() => {
              setStep('input');
              setJob(null);
              setResults([]);
              setUrlText('');
              setError(null);
            }}
          >
            Start another job
          </Button>
          <Link href="/investigations">
            <Button variant="ghost">
              View investigations <ArrowRight size={13} />
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

function ResultRow({ result }: { result: BulkScanJobResult }) {
  const isPending = result.status === 'pending';
  const isFailed = result.status === 'failed';
  const isOk = result.status === 'ok';

  return (
    <div className={`flex items-center gap-4 px-4 py-3 rounded-sm border text-sm transition-colors ${
      isPending ? 'border-border-1 bg-bg-elev opacity-50' :
      isFailed ? 'border-danger/30 bg-danger/5' :
      'border-border-1 bg-bg-elev'
    }`}>
      <div className="shrink-0">
        {isPending && <Clock size={14} className="text-fg-mute" />}
        {result.status === 'running' && <Loader2 size={14} className="text-accent animate-spin" />}
        {isFailed && <XCircle size={14} className="text-danger" />}
        {isOk && <CheckCircle size={14} className="text-tier-low" />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs text-fg-dim truncate" title={result.url}>{result.url}</p>
        {isFailed && result.error && (
          <p className="text-xs text-danger mt-0.5 truncate">{result.error}</p>
        )}
      </div>
      {isOk && result.tier && (
        <div className="flex items-center gap-3 shrink-0">
          <TierBadge tier={result.tier as any} size="sm" />
          {result.probability != null && (
            <span className="font-mono text-xs text-fg-dim">
              {Math.round(result.probability * 100)}%
            </span>
          )}
          {result.slug && (
            <Link
              href={`/investigations/${result.slug}`}
              className="text-accent hover:text-accent-2 font-mono text-2xs uppercase tracking-wider flex items-center gap-1"
            >
              View <ArrowRight size={10} />
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    queued: 'text-fg-mute border-border-2',
    running: 'text-accent border-accent/40 bg-accent/10 animate-pulse',
    done: 'text-tier-low border-tier-low/40 bg-tier-low/10',
    failed: 'text-danger border-danger/40 bg-danger/10',
  };
  return (
    <span className={`px-2 py-0.5 rounded-sm border font-mono text-2xs uppercase tracking-wider ${styles[status] ?? styles.queued}`}>
      {status}
    </span>
  );
}
