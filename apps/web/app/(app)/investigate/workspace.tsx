'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Plus, Sparkles } from 'lucide-react';
import { apiClient, ApiError, type CommenterScanResult, type ComprehensiveScanResult } from '@/lib/api';
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

  const runScan = async (url: string) => {
    setScanUrl(url);
    setState((s) => ({ ...s, pending: true, error: null, data: null, selectedId: null }));
    try {
      const body = await apiClient<ComprehensiveScanResult>('/v1/scan/link', {
        method: 'POST',
        body: JSON.stringify({ url, max_commenters: batchSize }),
      });
      // Defensive: a 200 with no usable payload (e.g. an upstream timeout that
      // returned an empty body) must not silently fall back to the empty state.
      if (!body || typeof body !== 'object' || !('overall_tier' in body)) {
        throw new Error(
          'The scan finished but returned no result — it likely timed out. ' +
            'Try again, or lower the batch size.',
        );
      }
      setState({ data: body, selectedId: null, pending: false, error: null, loadingMore: false });
      router.refresh();   // refresh credits chip + recent investigations
    } catch (e) {
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

  const loadMore = async () => {
    if (!state.data || !state.data.next_page_token) return;
    setState((s) => ({ ...s, loadingMore: true, error: null }));
    try {
      const body = await apiClient<ComprehensiveScanResult>('/v1/scan/link', {
        method: 'POST',
        body: JSON.stringify({
          url: scanUrl,
          max_commenters: batchSize,
          start_page_token: state.data.next_page_token,
          investigation_slug: state.data.investigation_slug,
        }),
      });
      // Append new commenters to existing
      setState((prev) => {
        if (!prev.data) return { ...prev, data: body, loadingMore: false };
        const existing = prev.data.video?.commenters || [];
        const incoming = body.video?.commenters || [];
        const seen = new Set(existing.map((c) => c.external_id));
        const merged = [...existing];
        for (const c of incoming) {
          if (!seen.has(c.external_id)) {
            merged.push(c);
            seen.add(c.external_id);
          }
        }
        return {
          ...prev,
          loadingMore: false,
          data: {
            ...body,
            quota_used: (prev.data.quota_used || 0) + body.quota_used,
            video: body.video ? { ...body.video, commenters: merged, commenter_count: merged.length } : null,
          },
        };
      });
      router.refresh();
    } catch (e) {
      setState((s) => ({
        ...s,
        loadingMore: false,
        error: e instanceof ApiError ? e.message : 'Failed to load more.',
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
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Workspace
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">Investigate</h1>
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
        <div className="rounded-sm border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger font-mono">
          {state.error}
        </div>
      )}

      <LoadingOverlay active={state.pending} />

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
                <CommenterDetail c={selectedCommenter} />
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
          <div className="absolute -top-16 -right-10 w-48 h-48 rounded-full bg-accent/[0.06] blur-3xl pointer-events-none" aria-hidden />
          <div className="relative flex gap-4">
            <div className="shrink-0 w-12 h-12 rounded-lg bg-accent/[0.08] border border-accent/20 flex items-center justify-center text-accent">
              <Sparkles size={22} />
            </div>
            <div>
              <CardLabel>Empty workspace</CardLabel>
              <CardTitle>Paste a YouTube link above to begin</CardTitle>
              <p className="text-sm text-fg-dim leading-relaxed max-w-xl">
                Every comprehensive scan analyzes the video, every commenter,
                their recent histories, and cross-account coordination signals.
                Results are saved as an investigation you can return to later.
              </p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
