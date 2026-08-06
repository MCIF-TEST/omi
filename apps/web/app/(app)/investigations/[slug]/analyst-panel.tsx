'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, Loader2, ShieldCheck, TriangleAlert, Users } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { AnalystLoading } from './analyst-loading';
import { SignalBreakdown } from '@/components/shared/signal-breakdown';
import { ExportResults } from '@/components/shared/export-results';
import type { ScannedAccount } from '@/lib/investigation-export';
import { failureReason } from '@/lib/analyst-failure';
import {
  apiClient,
  ApiError,
  VERDICT_LABELS,
  type AnalystResponse,
  type AnalystAssessment,
  type AnalystEvidenceItem,
  type CommenterAssessment,
  type CompletionStatus,
  type ComprehensiveSection,
  type ComprehensiveSections,
  type Tier,
} from '@/lib/api';

const POLL_INTERVAL_MS = 2500;
// Opening an investigation loads its SAVED assessment: a model-backed result shows immediately (no
// re-run), and while a generation is still in flight, the one scheduled at scan time, or the
// backend's one-shot auto-heal of an inconclusive/floored result. We hold the loading screen and
// poll until it lands. We never force a re-run from here. ~520s of polling matches the server's
// 500s generation timeout, so the wait ends when the real result does.
// ~10 min of polling. A batched run issues its model calls ONE AT A TIME (so the first accounts
// land as early as possible), which means the wall-clock total grows with the batch count, but this
// budget RESETS every time a new batch's results land (see the 'partial' branch), so it is really
// "10 minutes without visible progress". A scan that keeps delivering batches is never cut off here.
const MAX_POLLS = 240;

// A transport failure is not an answer, so it must not end the wait.
//
// A batched run polls every 2.5s for up to 10 minutes, which is ~240 fetches. Treating ONE failed
// fetch as terminal meant a single dropped connection anywhere in that sequence threw away a
// generation that was still running on the server, and the customer had already paid a credit for
// it. It fires most reliably during an API restart, which is exactly when a deploy is going out.
//
// So a dropped connection is retried with backoff and only reported once the API has been
// unreachable for about a minute. These retries deliberately do NOT consume the poll budget: that
// budget measures "how long since the analyst last made progress", and a failed request is not
// evidence either way.
const MAX_TRANSPORT_FAILS = 6;
const TRANSPORT_BACKOFF_CAP_MS = 15000;

// Dev-only Production Verification Mode (Phase 5C). OFF for normal users; enabled on demand with the
// URL query `?verify=1` (or `?debug=1`), or always-on where the deploy sets NEXT_PUBLIC_OMI_VERIFY_MODE=1.
// Purely a read-only diagnostic surface over the existing forensic trace, it changes no data.
function verificationEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_OMI_VERIFY_MODE === '1') return true;
  if (typeof window === 'undefined') return false;
  const q = new URLSearchParams(window.location.search);
  return q.has('verify') || q.has('debug');
}

/**
 * Minimum UI to exercise the Omi Analyst endpoint (Sprint 001).
 * POST -> 503 (disabled) | 202 (generating -> poll) | 200 (assessment).
 * The assessment is a recommendation bounded by the engine's evidence; it never
 * recomputes a score. Off by default, the disabled state degrades gracefully.
 */
export function AnalystPanel({
  slug,
  scanned = [],
  createdAt,
}: {
  slug: string;
  /** Every account this scan scored, projected server-side. Feeds the CSV / clipboard export, which
   *  covers the whole investigation rather than only the accounts the analyst reached. */
  scanned?: ScannedAccount[];
  createdAt?: string;
}) {
  const [assessment, setAssessment] = useState<AnalystAssessment | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [disabled, setDisabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startRef = useRef<number>(0);
  const lastBatchDoneRef = useRef<number>(0);
  // Most accounts published so far in THIS run, so a stale or duplicate poll cannot walk it back.
  const maxScoredRef = useRef<number>(0);

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  // Tick a real elapsed clock while the AI runs, so a two-minute wait reads as deliberate.
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(
      () => setElapsedSec(Math.round((Date.now() - startRef.current) / 1000)),
      500,
    );
    return () => clearInterval(t);
  }, [pending]);

  const post = (refresh: boolean) =>
    apiClient<AnalystResponse>(
      `/v1/investigations/${slug}/analyst${refresh ? '?refresh=true' : ''}`,
      { method: 'POST' },
    );

  const run = async (refresh: boolean) => {
    setError(null);
    setDisabled(false);
    setElapsedSec(0);
    startRef.current = Date.now();
    setPending(true);
    // Reset per-run, here rather than at the call sites, so a slug change starts clean too.
    lastBatchDoneRef.current = 0;
    maxScoredRef.current = 0;
    let polls = 0;
    let transportFails = 0;

    const step = async (doRefresh: boolean): Promise<void> => {
      try {
        const r = await post(doRefresh);
        // The API answered, so whatever the answer is, the connection is healthy again.
        transportFails = 0;
        // A SAVED assessment (model-backed, or the deterministic floor) is the previous result. Show
        // it as-is. We never force a re-run on open; the backend alone decides when an inconclusive
        // (floored) result is worth regenerating, and does so exactly once, returning 202 while it runs.
        if (r.status === 'ready' && r.assessment) {
          setAssessment(r.assessment);
          setProvider(r.provider ?? null);
          setGeneratedAt(r.generated_at ?? null);
          setPending(false);
          return;
        }
        // Batched run in progress: render the finished batches' accounts NOW (first-to-last) and
        // keep polling for the rest. Every batch that lands resets the poll budget, a many-batch
        // scan visibly making progress is never timed out.
        if (r.status === 'partial' && r.assessment) {
          const done = r.assessment.batching?.done ?? 0;
          if (done > lastBatchDoneRef.current) {
            lastBatchDoneRef.current = done;
            polls = 0;
          }
          // Defence in depth against a reset the user should never see. The server now refuses to
          // publish one run's progress over a further-along live run, so this should not trigger;
          // it is here because the cost of being wrong is asymmetric. Showing fewer accounts than
          // a moment ago reads as the product losing paid-for work, while ignoring one stale poll
          // costs nothing: the next poll 2.5s later corrects it.
          //
          // Both counters reset in `run(true)`, so an explicit Retry still shows its fresh run.
          const scored = r.assessment.commenter_assessments?.length ?? 0;
          if (scored >= maxScoredRef.current) {
            maxScoredRef.current = scored;
            setAssessment(r.assessment);
            setProvider(r.provider ?? null);
            setGeneratedAt(r.generated_at ?? null);
          }
        }
        // 202 generating, a scan-time generation or the backend's one-shot auto-heal is in flight.
        // Hold the loading screen and poll until it lands.
        if (polls++ >= MAX_POLLS) {
          setError('The AI analysis is taking longer than usual. It keeps running on the server. Reload in a moment to pick it up.');
          setPending(false);
          return;
        }
        pollRef.current = setTimeout(() => { void step(false); }, POLL_INTERVAL_MS);
      } catch (e) {
        // A dropped connection, or a gateway that has no server to talk to, says nothing about the
        // generation. Both happen while the API restarts. Ride them out rather than discarding a run
        // that is still going. 503 is deliberately NOT here: our own API returns it to mean the
        // analyst is switched off, which is a real answer and not a transport fault.
        const transport = e instanceof TypeError
          || (e instanceof ApiError && (e.status === 502 || e.status === 504));
        if (transport && ++transportFails <= MAX_TRANSPORT_FAILS) {
          const wait = Math.min(POLL_INTERVAL_MS * 2 ** (transportFails - 1),
                                TRANSPORT_BACKOFF_CAP_MS);
          pollRef.current = setTimeout(() => { void step(false); }, wait);
          return;
        }
        if (e instanceof ApiError && e.status === 503) {
          setDisabled(true);
        } else if (e instanceof ApiError) {
          // Carries the server's own detail, or a status-specific description (lib/api.ts). Either way
          // it names something actionable rather than "it failed".
          setError(e.message);
        } else if (e instanceof TypeError) {
          // fetch() rejects with TypeError only when the request never completed, the connection was
          // refused, reset, or cut mid-flight. That is a different problem from the server saying no,
          // and it used to be reported with the same generic sentence, which hid the distinction that
          // matters most when diagnosing: was the API even reached?
          setError(
            'Could not reach the analysis service for about a minute, after several retries. Your ' +
            'analysis is most likely still running on the server, and no credit is spent by ' +
            'waiting. Reload the page in a minute to pick it up.',
          );
        } else {
          setError(e instanceof Error && e.message ? e.message : 'Failed to generate the assessment.');
        }
        setPending(false);
      }
    };

    await step(refresh);
  };

  // Auto-load on mount: the analyst now runs server-side for every investigation
  // (scheduled at scan time), so surface its cached assessment automatically, the AI
  // reading is part of the report, not a manual action. A cached result returns
  // immediately (no new model call); 503 degrades to the graceful "not enabled" notice.
  useEffect(() => {
    void run(false);
    // Fire once per investigation; `run` is stable for the component's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  return (
    <Card>
      <div className="flex flex-col gap-2 mb-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex items-center gap-3 flex-wrap">
          <CardLabel className="m-0 flex items-center gap-1.5">
            <Brain size={11} /> Omi Analyst assessment
          </CardLabel>
          {customerProviderLabel(provider) && (
            <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
              ▸ {customerProviderLabel(provider)}
            </span>
          )}
        </div>
        {/* Deliberately outside the assessment branches below. The engine scored every selected
            account even when the model reached none of them, so the export must not disappear with
            the analyst's prose: an investigation that was paid for is still exportable. */}
        <ExportResults
          slug={slug}
          createdAt={createdAt}
          scanned={scanned}
          reads={assessment?.commenter_assessments}
        />
      </div>

      {disabled ? (
        <p className="text-sm text-fg-dim flex items-start gap-2">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-fg-mute" />
          Omi Analyst reasoning isn&apos;t enabled on this server yet. The structured,
          evidence-bounded assessment becomes available once the reasoning layer is
          turned on, the investigation evidence above is unaffected.
        </p>
      ) : pending && !assessment ? (
        // The analyst runs automatically for every investigation. Hold a real loading screen while
        // the model response is on its way, it fills in the moment the result lands. Once a
        // batched run's FIRST batch lands, the partial assessment renders below instead (with a
        // progress strip), so results appear first-to-last while later batches still generate.
        // `scanned` is every account the engine scored, so the batch count is derivable here
        // without waiting for the server: the user sees "batch 1 of 4" immediately instead of a
        // shapeless spinner that tells them nothing about how long this will take.
        <AnalystLoading elapsedSec={elapsedSec} accounts={scanned.length} />
      ) : !assessment ? (
        <p className="text-sm text-fg-dim flex items-start gap-2">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-fg-mute" />
          The Omi Analyst’s structured reading of this investigation will appear here. It interprets
          the evidence the engine already produced; it never recomputes a score.
        </p>
      ) : (
        <>
          {assessment.batching && !assessment.batching.complete && (
            <BatchProgressStrip
              batching={assessment.batching}
              elapsedSec={elapsedSec}
              scored={assessment.commenter_assessments?.length ?? 0}
            />
          )}
          <AssessmentView
            a={assessment}
            slug={slug}
            onRetry={() => void run(true)}
            busy={pending}
          />
          {/* The same live state repeated where the results END: the user reading down the list
              reaches the last scored account here, and needs to know more are still coming rather
              than assuming the scan stopped short. */}
          {assessment.batching && !assessment.batching.complete && (
            <BatchTrailingNotice
              batching={assessment.batching}
              scored={assessment.commenter_assessments?.length ?? 0}
            />
          )}
          {/* Finished, but a batch produced nothing. Say so plainly rather than letting a short list
              read as the whole answer, and offer the retry that would fill it in. */}
          {assessment.batching
            && assessment.batching.complete
            && (assessment.batching.landed ?? assessment.batching.total)
               < assessment.batching.total && (
            <IncompleteCoverageNotice
              batching={assessment.batching}
              onRetry={() => void run(true)}
              busy={pending}
            />
          )}
        </>
      )}

      {assessment && verificationEnabled() && (
        <VerificationPanel a={assessment} provider={provider} generatedAt={generatedAt} />
      )}

      {error && (
        <p className="mt-3 text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          {error}
        </p>
      )}
    </Card>
  );
}

/**
 * Live progress for a batched run. Accounts are scored one ≤cap-account batch at a time, merged
 * first-to-last, so batch 1's results are readable while the rest still generate. Purple = the AI
 * layer. The results shown below the strip are FINAL for the batches already landed; later batches
 * append underneath in order.
 */
function BatchProgressStrip({
  batching,
  elapsedSec,
  scored,
}: {
  batching: NonNullable<AnalystAssessment['batching']>;
  elapsedSec: number;
  /** Accounts actually returned so far, the real count, not done × batch_size (the final batch is
   *  usually partial, which would overstate it). */
  scored: number;
}) {
  const pct = Math.max(4, Math.round((batching.done / Math.max(1, batching.total)) * 100));
  return (
    <div className="mb-4 rounded-lg border border-violet/25 bg-violet/[0.06] px-3.5 py-2.5">
      <div className="flex items-center justify-between gap-2 mb-1.5 flex-wrap">
        <span className="font-mono text-2xs tracking-[0.14em] uppercase text-violet-2 flex items-center gap-1.5">
          <Loader2 size={11} className="animate-spin" />
          Scoring in batches: {batching.done} of {batching.total} done
        </span>
        <span className="font-mono text-2xs text-fg-mute tabular-nums">
          {scored} account{scored === 1 ? '' : 's'} scored · {elapsedSec}s
        </span>
      </div>
      <div className="h-1 rounded-full bg-bg-inset overflow-hidden" role="progressbar"
           aria-valuenow={batching.done} aria-valuemin={0} aria-valuemax={batching.total}
           aria-label={`Analysis batches completed: ${batching.done} of ${batching.total}`}>
        <div
          className="h-full rounded-full bg-violet-dim transition-[width] duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-2xs text-fg-mute leading-relaxed">
        The scores below are final for the accounts already analyzed. The remaining accounts are being
        analyzed right now and will appear underneath, in order.
      </p>
    </div>
  );
}

/**
 * The bottom bookend of a batched run. Someone reading down the results reaches the end of the
 * scored accounts here, without this, a 100-account scan showing 25 results looks finished-and-short
 * rather than still-running.
 */
function BatchTrailingNotice({
  batching,
  scored,
}: {
  batching: NonNullable<AnalystAssessment['batching']>;
  scored: number;
}) {
  const remaining = Math.max(0, batching.total - batching.done);
  return (
    <div
      className="mt-4 rounded-lg border border-dashed border-violet/30 bg-violet/[0.04] px-3.5 py-3 flex items-center gap-2.5"
      aria-live="polite"
    >
      <Loader2 size={13} className="animate-spin text-violet-2 shrink-0" />
      <p className="text-2xs text-fg-dim leading-relaxed">
        <span className="text-fg-dim font-medium">{scored} account{scored === 1 ? '' : 's'} analyzed.</span>{' '}
        Still analyzing the rest. {remaining} more batch{remaining === 1 ? '' : 'es'} to go. Each batch
        is a separate pass, so a large scan can take up to 10 minutes to finish. New accounts appear
        here as each batch lands; you don&apos;t need to wait on this page.
      </p>
    </div>
  );
}

/**
 * The run finished, but one or more batches came back empty (a failed model call), so some selected
 * accounts have no assessment. Stating that is the honest thing to do, a silently short list reads
 * as "these were all the accounts". The retry re-runs the generation for the whole investigation.
 */
function IncompleteCoverageNotice({
  batching,
  onRetry,
  busy,
}: {
  batching: NonNullable<AnalystAssessment['batching']>;
  onRetry: () => void;
  busy: boolean;
}) {
  const missing = batching.total - (batching.landed ?? batching.total);
  return (
    <div className="mt-4 rounded-lg border border-warn/35 bg-warn/[0.07] px-3.5 py-3 flex items-start gap-2.5 flex-wrap">
      <TriangleAlert size={13} className="mt-0.5 shrink-0 text-warn" />
      <p className="text-2xs text-fg-dim leading-relaxed flex-1 min-w-[12rem]">
        {batching.done} of {batching.total} batches were analyzed. {missing} batch
        {missing === 1 ? '' : 'es'} came back empty, so some of the accounts you selected have no
        assessment below. The scores that are shown are final.
      </p>
      <button
        type="button"
        onClick={onRetry}
        disabled={busy}
        className="btn-slab h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim disabled:opacity-40"
      >
        {busy ? <Loader2 size={12} className="animate-spin" /> : null}
        Retry analysis
      </button>
    </div>
  );
}

function verdictLabel(v: string): string {
  return (VERDICT_LABELS as Record<string, string>)[v] ?? v;
}

// The corroboration methods, and which of them are DISCRIMINATIVE of coordination (a maximal
// 'coordinated' read requires >=1 discriminative method AND single_axis_capped === false). Mirrors
// the backend gate. Surfaced here so the panel shows WHY a coordinated read is (or isn't) permitted.
const METHOD_LABELS: Record<string, string> = {
  fingerprint_cluster: 'fingerprint',
  co_engagement: 'co-engagement',
  co_tag: 'co-tag',
  temporal_semantic: 'temporal+semantic',
  style_match: 'style match',
  age_cohort: 'age cohort',
  reply_pods: 'reply pods',
};
const DISCRIMINATIVE_METHODS = new Set(['fingerprint_cluster', 'co_engagement', 'co_tag']);

// The engine's corroboration state (echoed onto the assessment). Rendered as structured chips, the
// discriminative methods that fired, plus the single-axis-cap and convergence flags, so the reader
// can see the coordination gate directly instead of inferring it from prose.
function CorroborationStrip({ corr }: { corr?: AnalystAssessment['corroboration'] }) {
  if (!corr) return null;
  const methods = corr.discriminative_methods ?? [];
  return (
    <div className="flex items-center gap-1.5 flex-wrap font-mono text-2xs">
      <span className="uppercase tracking-wider text-fg-mute">Corroboration</span>
      {methods.length > 0 ? (
        methods.map((m) => (
          <span
            key={m}
            className={`rounded-full border px-1.5 py-0.5 ${
              DISCRIMINATIVE_METHODS.has(m)
                ? 'border-accent/50 text-accent'
                : 'border-border-1/60 text-fg-mute'
            }`}
          >
            {METHOD_LABELS[m] ?? m}
          </span>
        ))
      ) : (
        <span className="text-fg-faint">no discriminative method fired</span>
      )}
      {corr.single_axis_capped && (
        <span
          className="rounded-full border border-tier-moderate/40 text-tier-moderate px-1.5 py-0.5"
          title="One axis carried the score; the coordinated read is capped."
        >
          single-axis capped
        </span>
      )}
      {corr.convergence && (
        <span
          className="rounded-full border border-border-1/60 text-fg-mute px-1.5 py-0.5"
          title="Two or more independent detectors converged."
        >
          convergence
        </span>
      )}
    </div>
  );
}

// Supplemental signals (e.g. AI-writing). Reported as neutral context that carries ZERO suspicion
// weight. Surfaced as its own labeled block so it can never be mistaken for incriminating evidence.
function SupplementalContext({ items }: { items?: { signal: string; note: string }[] }) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <CardLabel className="mb-2">Context · zero suspicion weight</CardLabel>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="text-xs text-fg-dim flex gap-2 leading-relaxed">
            <span className="text-fg-mute">◇</span>
            <span>
              <span className="text-fg-mute font-mono">{it.signal}</span>. {it.note}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// The explicit legitimate-coordination hypothesis the analyst considered (precision-frontier
// discipline). Present for coordination reads; surfaced verbatim from the structured field.
function LegitimateHypothesis({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <div>
      <CardLabel className="mb-2">Legitimate-coordination hypothesis</CardLabel>
      <p className="text-xs text-fg-dim leading-relaxed">{text}</p>
    </div>
  );
}

// What a CUSTOMER may see about how the analysis was produced.
//
// The raw `provider` is an internal transport label ("openrouter-omi-analyst-v1") and was rendered
// straight into the card header, so every customer read the name of the model vendor we happen to
// route through. That is our supplier, not their concern, and it is a detail we must stay free to
// change without it appearing on a page somebody screenshots.
//
// The card header already says "Omi Analyst assessment", so the normal path needs no chip at all.
// The one thing worth surfacing is the degraded case, named in product terms. The raw string stays
// available to operators in the verification panel.
function customerProviderLabel(provider: string | null): string | null {
  const p = (provider ?? '').toLowerCase();
  if (!p) return null;
  if (p.includes('fallback') || p.includes('deterministic') || p.includes('floor')) {
    return 'written analysis unavailable';
  }
  return null;
}

// Whether the AI model actually authored this assessment. Prefer the explicit trace flag; fall back to the
// governance provider string for assessments persisted before the trace existed. When false, the
// synthesis prose is the deterministic Floor's, it must NEVER be shown as AI reasoning.
function isModelBacked(a: AnalystAssessment): boolean {
  if (typeof a.investigation_trace?.model_backed === 'boolean') return a.investigation_trace.model_backed;
  const provider = a.governance?.provider ?? '';
  return provider.length > 0 && !/fallback|deterministic|floor/i.test(provider);
}

// ── Phase 5C: dev-only Production Verification panel ──────────────────────────────────────────────
// A read-only diagnostic surface over the persisted forensic trace. It proves which gateway + model
// served THIS investigation (or that the deterministic Floor stood in), whether validation passed, and
// the latency/token/cost of the call. Gated by verificationEnabled(); never shown to normal users and
// never alters any data. No secrets are present in the trace it reads.
function fmtMs(v?: number | null): string {
  return typeof v === 'number' ? `${Math.round(v)} ms` : '-';
}
function fmtCost(v?: number | null): string {
  return typeof v === 'number' ? `$${v.toFixed(6)}` : '-';
}
function yn(v: boolean | undefined | null): string {
  return v === true ? 'yes' : v === false ? 'no' : '-';
}

function VerificationPanel({
  a, provider, generatedAt,
}: { a: AnalystAssessment; provider: string | null; generatedAt: string | null }) {
  const t = a.investigation_trace ?? {};
  const c = a.completion;
  const aiBacked = t.model_backed === true;
  const rows: [string, React.ReactNode][] = [
    ['Provider', t.provider ?? provider ?? '-'],
    ['Served model', t.served_model ?? t.requested_model ?? '-'],
    ['Served model verified', t.served_model_verified == null
      ? '-'
      : t.served_model_verified
        ? `yes. ${t.served_model_expected ?? 'expected model'}`
        : `NO: expected ${t.served_model_expected ?? '?'}, served ${t.served_model ?? '?'}`],
    ['Preset', t.openrouter_preset ?? '-'],
    ['Protocol version', t.master_prompt_version ?? '-'],
    ['Protocol hash', t.master_prompt_hash ?? '-'],
    ['Schema id / version', `${t.canonical_schema_id ?? '-'} / v${(a as { schema_version?: number }).schema_version ?? '-'}`],
    ['Model-backed', yn(t.model_backed)],
    ['Request completed', yn(t.request_completed)],
    ['JSON received', yn(t.json_received)],
    ['Validation passed', yn(t.validation_passed)],
    ['Governor verdict', t.governor_verdict ?? '-'],
    ['Fallback used', yn(!aiBacked)],
    ['Fallback reason', t.fallback_reason ?? '-'],
    ['Latency', fmtMs(t.endpoint_latency_ms)],
    ['Input tokens', t.input_tokens ?? '-'],
    ['Output tokens', t.output_tokens ?? '-'],
    ['Total tokens', t.total_tokens ?? '-'],
    ['Estimated cost', fmtCost(t.endpoint_cost_usd)],
    ['Request id', t.endpoint_request_id ?? '-'],
    ['HTTP status', t.response_status ?? '-'],
    ['Endpoint error', t.endpoint_error ?? '-'],
    ['Generated at', generatedAt ?? '-'],
    // Phase 5H. Full-investigation completion certification
    ['completion', ''],
    ['Completion', c ? (c.complete ? 'complete' : `incomplete: ${c.incomplete_kind ?? '-'}`) : '-'],
    ['Commenters analyzed / expected',
      c ? `${c.assessed_commenters} / ${c.represented_commenters + c.omitted_input_commenters}` : '-'],
    ['Stopped on token limit', yn(c?.stopped_on_token_limit)],
    ['JSON complete', yn(c?.json_complete)],
    ['Schema valid', yn(c?.schema_valid)],
    ['Governor valid', yn(c?.governor_valid)],
    ['Completion budget', c?.max_output_tokens ?? t.max_output_tokens ?? '-'],
    ['Actual output size', c?.output_tokens ?? '-'],
    ['Est. remaining commenters', c?.estimated_remaining_commenters ?? '-'],
  ];
  return (
    <details className="mt-4 rounded-sm border border-dashed border-accent/40 bg-bg-elev-2/40 open:bg-bg-elev-2">
      <summary className="cursor-pointer select-none list-none px-3 py-2 flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <span
            className={`font-mono text-2xs tracking-wider uppercase rounded-full border px-2 py-0.5 ${
              aiBacked
                ? 'border-tier-low/50 text-tier-low bg-tier-low/10'
                : 'border-tier-moderate/50 text-tier-moderate bg-tier-moderate/10'
            }`}
          >
            {aiBacked
              ? '🟢 AI Investigation'
              : '🟡 Deterministic Floor'}
          </span>
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">
            production verification
          </span>
        </span>
        <span className="text-fg-faint text-2xs group-open:hidden">dev only</span>
      </summary>
      <div className="px-3 pb-3 overflow-x-auto">
        <table className="w-full text-2xs font-mono">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-t border-border-1/40">
                <td className="py-1 pr-3 text-fg-mute uppercase tracking-wider whitespace-nowrap align-top">{k}</td>
                <td className="py-1 text-fg-dim break-all">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

// THE OMI SCORE: the single composite authenticity-risk score (0-100), the investigation's headline
// figure. Higher = stronger evidence of inauthentic/coordinated behavior. Rendered as the number plus a
// tier-colored bar (score/100). This is the only investigation score; the legacy inauthenticity
// probability is retired.
function OmiScore({ score, tier }: { score: number; tier: Tier }) {
  const s = Math.max(0, Math.min(100, Math.round(score ?? 0)));
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-baseline gap-1 shrink-0" title="OMI score. Composite authenticity-risk, 0-100.">
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute mr-1">OMI</span>
        <span className="stat-value text-2xl font-semibold text-fg tabular-nums">{s}</span>
        <span className="font-mono text-2xs text-fg-mute">/100</span>
      </div>
      <ProbabilityBar value={s / 100} tier={tier} className="flex-1" showLabel={false} />
    </div>
  );
}

function AssessmentView(
  { a, slug, onRetry, busy }:
  { a: AnalystAssessment; slug: string; onRetry: () => void; busy: boolean },
) {
  // A batched run that is still going is NOT a failed run. `batching.complete === false` means more
  // batches are queued, and a later one can still land a model-backed result that makes the merged
  // assessment model-backed. Showing the terminal "could not be produced" notice here contradicts the
  // progress strip rendered directly above it ("1 of 4 done, 3 more batches to go") and tells the user
  // the scan failed while it is visibly still working. Wait for the run to finish before judging it.
  const stillBatching = a.batching ? a.batching.complete === false : false;
  if (!isModelBacked(a) && stillBatching) {
    return (
      <p className="text-sm text-fg-dim">
        Waiting for the first completed batch. Account scores appear above as each one lands.
      </p>
    );
  }
  // Product-cutover rule: only AI-authored assessments render as AI reasoning. If the model
  // was not reached, the deterministic Floor stood in. We must NOT present its synthesized verdict /
  // headline / assessment / evidence as though the AI wrote it.
  if (!isModelBacked(a)) return <AiUnavailable a={a} onRetry={onRetry} busy={busy} />;

  return (
    <div className="space-y-5">
      {/* ── LEAD INVESTIGATOR SYNTHESIS (Omi Analyst) ──────────────────────── */}
      <div className="space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <TierBadge tier={a.suspicion_tier as Tier} />
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute border border-border-hot px-2.5 py-1 rounded-full bg-bg-elev-2">
            {verdictLabel(a.verdict)} · recommended
          </span>
          <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute">
            {a.confidence_band} confidence
          </span>
          {a.coordination_label && (
            <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute border border-border-1/60 px-2.5 py-1 rounded-full bg-bg-elev-2">
              coordination: {a.coordination_label}
            </span>
          )}
        </div>

        {/* THE OMI SCORE: the analyst's single composite authenticity-risk score (0-100), the headline
            figure. Replaces the legacy inauthenticity probability. Rendered as the big number + a
            tier-colored bar. */}
        <OmiScore score={a.omi_score} tier={a.suspicion_tier as Tier} />

        <CorroborationStrip corr={a.corroboration} />

        {a.headline && <p className="text-sm text-fg leading-relaxed">{a.headline}</p>}
        {a.assessment && (
          <p className="text-sm text-fg-dim leading-relaxed whitespace-pre-line">{a.assessment}</p>
        )}

        <div className="grid sm:grid-cols-2 gap-4">
          <EvidenceList label="Evidence for" tone="raise" items={a.evidence_for} />
          <EvidenceList label="Evidence against" tone="lower" items={a.evidence_against} />
        </div>

        <PlainList label="Confidence & uncertainty" lead={a.confidence_rationale} items={a.uncertainty} />
        <PlainList label="What would change this" items={a.what_would_change_this} />
        <SupplementalContext items={a.supplemental_context} />
        <LegitimateHypothesis text={a.legitimate_hypothesis} />
      </div>

      {/* ── PER-ACCOUNT ASSESSMENTS (one AI reading per commenter, over the ONE response) ── */}
      <CommenterAssessments items={a.commenter_assessments} completion={a.completion} slug={slug} />

      {/* ── DOMAIN REASONING (six views over the ONE comprehensive response) ── */}
      <DomainReasoning
        sections={a.comprehensive_sections}
        validation={a.comprehensive_validation}
      />

      {a.governance && (
        <p className="text-2xs font-mono text-fg-mute flex items-center gap-1.5 flex-wrap">
          <ShieldCheck size={11} className="text-accent shrink-0" />
          Governor {a.governance.verdict ?? 'n/a'} · {a.governance.provider ?? 'floor'}
          {typeof a.governance.latency_ms === 'number' ? ` · ${Math.round(a.governance.latency_ms)}ms` : ''}
        </p>
      )}
      {a.limits_statement && (
        <p className="text-2xs text-fg-faint border-t border-border-1/60 pt-3 leading-relaxed">
          {a.limits_statement}
        </p>
      )}
    </div>
  );
}

// The written analysis could not be produced for this scan. This is a FINISHED state, not a pending
// one: the run completed, the model was unreachable or its answer was rejected, and the deterministic
// Floor stood in. The old copy here said "isn't ready yet, check back in a moment", which described a
// pending state that no longer existed and left the user with nothing to do but re-run the whole scan
// and spend another credit. It also read as though nothing worked, when in fact every account score
// below is real. Say what happened, keep the scores, and offer the free retry.
// The technical forensic diagnostic stays behind verification mode.
function AiUnavailable(
  { a, onRetry, busy }: { a: AnalystAssessment; onRetry: () => void; busy: boolean },
) {
  const t = a.investigation_trace ?? {};
  const verbose = verificationEnabled();
  const reason = failureReason(t);
  return (
    <div className="rounded-lg border border-warn/35 bg-warn/[0.07] px-3.5 py-3 space-y-2.5">
      <div className="flex items-start gap-2.5">
        <TriangleAlert size={14} className="mt-0.5 shrink-0 text-warn" />
        <div className="text-sm text-fg-dim leading-relaxed flex-1 min-w-[12rem]">
          <p>
            The written analysis could not be produced for this scan.
            {reason ? ` ${reason}` : ''}
          </p>
          <p className="mt-1.5 text-xs text-fg-mute">
            Every account score below is complete and unaffected. Only the Omi Analyst&rsquo;s written
            read is missing. Retrying runs a fresh analysis and does not cost a credit.
          </p>
          {verbose && <AiUnavailableDiagnostics t={t} governanceProvider={a.governance?.provider} />}
        </div>
        <button
          type="button"
          onClick={onRetry}
          disabled={busy}
          className="btn-slab h-8 px-3 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim disabled:opacity-40 shrink-0"
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : null}
          Retry analysis
        </button>
      </div>
    </div>
  );
}

// Dev-only forensic detail behind the AI-unavailable notice (shown with ?verify=1). Never shown to users.
function AiUnavailableDiagnostics(
  { t, governanceProvider }: { t: NonNullable<AnalystAssessment['investigation_trace']>; governanceProvider?: string },
) {
  const status = typeof t.response_status === 'number' ? t.response_status : null;
  const ok2xx = status !== null && status >= 200 && status < 300;
  const schemaErrs = t.canonical_validation_errors ?? [];
  const reason =
    t.fallback_reason
    ?? (t.endpoint_called === false ? 'endpoint not called (analyst disabled or no API key)'
      : ok2xx ? (schemaErrs.length
          ? 'model replied, but its output failed schema validation'
          : t.json_received === false ? 'model replied, but no JSON object was parsed from it'
          : 'model replied, but its output was not usable')
      : status !== null ? `gateway rejected the request (HTTP ${status})`
      : t.endpoint_error ? 'gateway error'
      : 'unknown');
  const diagnostics: [string, string][] = [
    ['provider', t.provider ?? governanceProvider ?? '-'],
    ['reason', reason],
    ...(status !== null ? [['http status', String(status)] as [string, string]] : []),
    ...(t.endpoint_error ? [['error', t.endpoint_error] as [string, string]] : []),
    ...(t.requested_model ? [['requested', t.requested_model] as [string, string]] : []),
    ...(t.served_model ? [['served', t.served_model] as [string, string]] : []),
    ...(t.finish_reason ? [['finish', t.finish_reason] as [string, string]] : []),
  ];
  return (
    <>
      <span className="block mt-1.5 text-2xs font-mono text-fg-faint">
        {diagnostics.map(([k, v]) => (
          <span key={k} className="mr-3 whitespace-nowrap">
            {k}: <span className="text-fg-mute">{v}</span>
          </span>
        ))}
      </span>
      {schemaErrs.length > 0 && (
        <span className="block mt-1.5 text-2xs font-mono text-fg-faint">
          schema errors:
          <ul className="mt-0.5 ml-3 list-disc space-y-0.5">
            {schemaErrs.slice(0, 8).map((e, i) => (
              <li key={i} className="text-fg-mute break-all">{e}</li>
            ))}
          </ul>
        </span>
      )}
    </>
  );
}

const DOMAIN_PANELS: { key: keyof ComprehensiveSections; title: string }[] = [
  { key: 'comment_reasoning', title: 'Comment analysis' },
  { key: 'commenter_history_reasoning', title: 'Commenter history' },
  { key: 'account_reasoning', title: 'Account analysis' },
  { key: 'narrative_reasoning', title: 'Narrative analysis' },
  { key: 'coordination_reasoning', title: 'Coordination analysis' },
  { key: 'campaign_reasoning', title: 'Campaign analysis' },
];

// The six per-domain reasoning sections of the single comprehensive AI response. Each panel is a
// pure view over the already-loaded assessment. Expanding a panel triggers NO request (no per-panel
// inference). Sections the model left empty are shown as "no reasoning provided" rather than hidden.
function DomainReasoning({
  sections,
  validation,
}: {
  sections?: ComprehensiveSections;
  validation?: AnalystAssessment['comprehensive_validation'];
}) {
  const present = DOMAIN_PANELS.filter(({ key }) => sections?.[key] !== undefined);
  if (present.length === 0) return null;
  return (
    <div className="border-t border-border-1/60 pt-4 space-y-2">
      <CardLabel className="flex items-center gap-1.5">
        <Brain size={11} /> Domain reasoning · one AI investigation
      </CardLabel>
      <div className="space-y-1.5">
        {present.map(({ key, title }) => (
          <DomainPanel
            key={key}
            title={title}
            section={sections?.[key]}
            unresolved={validation?.sections?.[key]?.unresolved}
          />
        ))}
      </div>
    </div>
  );
}

function DomainPanel({
  title,
  section,
  unresolved,
}: {
  title: string;
  section?: ComprehensiveSection;
  unresolved?: string[];
}) {
  const text = section?.assessment?.trim();
  const citations = section?.citations ?? [];
  const unresolvedSet = new Set(unresolved ?? []);
  return (
    <details className="group rounded-sm border border-border-1/60 bg-bg-elev-2/40 open:bg-bg-elev-2">
      <summary className="cursor-pointer select-none list-none px-3 py-2 text-xs font-mono uppercase tracking-wider text-fg-mute flex items-center justify-between gap-2">
        <span>{title}</span>
        <span className="text-fg-faint text-2xs group-open:hidden">expand</span>
        <span className="text-fg-faint text-2xs hidden group-open:inline">collapse</span>
      </summary>
      <div className="px-3 pb-3 space-y-2">
        {text ? (
          <p className="text-xs text-fg-dim leading-relaxed whitespace-pre-line">{text}</p>
        ) : (
          <p className="text-xs text-fg-faint italic">No reasoning provided for this domain.</p>
        )}
        {citations.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {citations.map((c, i) => {
              const bad = unresolvedSet.has(c);
              return (
                <span
                  key={i}
                  title={bad ? 'This citation does not resolve against the evidence.' : undefined}
                  className={`font-mono text-2xs rounded-full border px-1.5 py-0.5 ${
                    bad
                      ? 'text-danger border-danger/50 line-through'
                      : 'text-fg-mute border-border-1/60'
                  }`}
                >
                  {c}
                </span>
              );
            })}
          </div>
        )}
      </div>
    </details>
  );
}

// Per-account (per-commenter) AI assessments from the ONE comprehensive response. Each card pairs the
// model's per-account reasoning with the engine's echoed tier/probability (joined server-side, the model
// never emits a per-account number). When the model produced none, an honest empty state is shown instead
// of any deterministic fallback. `resolved: false` items (alias didn't map to a known commenter) are
// summarized as a count rather than shown as fabricated identities.
// Completion statistics, always shown so the user knows the AI coverage of THIS investigation
// (expected vs analyzed, the dynamic budget, actual output). Never hides an incomplete investigation.
function CompletionStats({ c }: { c: CompletionStatus }) {
  const expected = c.represented_commenters + c.omitted_input_commenters;
  const bits: string[] = [`${c.assessed_commenters}/${expected} analyzed`];
  if (typeof c.output_tokens === 'number' && c.max_output_tokens)
    bits.push(`${c.output_tokens.toLocaleString()}/${c.max_output_tokens.toLocaleString()} out tokens`);
  if (c.finish_reason) bits.push(`stop: ${c.finish_reason}`);
  return <p className="text-2xs font-mono text-fg-faint mt-0.5">{bits.join(' · ')}</p>;
}

function CompletionBanner({ c }: { c?: CompletionStatus }) {
  if (!c) return null;
  if (c.complete) {
    return (
      <div className="space-y-0.5">
        <p className="text-2xs font-mono uppercase tracking-wider text-tier-low flex items-center gap-1.5">
          <ShieldCheck size={11} className="shrink-0" />
          Complete · all {c.assessed_commenters} commenter{c.assessed_commenters === 1 ? '' : 's'} assessed
        </p>
        <CompletionStats c={c} />
      </div>
    );
  }
  return (
    <div className="rounded-sm border border-tier-moderate/40 bg-tier-moderate/[0.07] px-3 py-2 flex items-start gap-2">
      <TriangleAlert size={13} className="mt-0.5 shrink-0 text-tier-moderate" />
      <div className="min-w-0">
        <p className="text-2xs font-mono uppercase tracking-wider text-tier-moderate mb-0.5">
          Partial AI coverage · {c.assessed_commenters} of {c.represented_commenters + c.omitted_input_commenters} commenters assessed
        </p>
        <p className="text-xs text-fg-dim leading-relaxed">{c.reason}</p>
        {c.estimated_remaining_commenters > 0 && (
          <p className="text-2xs text-fg-faint mt-0.5">
            ~{c.estimated_remaining_commenters} commenter{c.estimated_remaining_commenters === 1 ? '' : 's'} remaining.
          </p>
        )}
        <CompletionStats c={c} />
      </div>
    </div>
  );
}

// Compact raw-metadata line for one account, the objective facts (followers, age, posts) the AI
// scored from, shown beside its OMI score. Only renders the facts that were collected.
function accountAgeDays(iso?: string): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((Date.now() - t) / 86_400_000));
}
function AccountMetadata({ r }: { r: CommenterAssessment }) {
  const bits: string[] = [];
  if (typeof r.follower_count === 'number') bits.push(`${r.follower_count.toLocaleString()} followers`);
  if (typeof r.following_count === 'number') bits.push(`${r.following_count.toLocaleString()} following`);
  const age = accountAgeDays(r.account_created_at);
  if (age !== null) bits.push(age < 365 ? `${age}d old` : `${(age / 365).toFixed(1)}y old`);
  if (typeof r.post_count === 'number') bits.push(`${r.post_count.toLocaleString()} posts`);
  if (bits.length === 0) return null;
  return <p className="font-mono text-2xs text-fg-faint">{bits.join(' · ')}</p>;
}

function CommenterAssessments({
  items, completion,
}: { items?: CommenterAssessment[]; completion?: CompletionStatus; slug: string }) {
  const rows = items ?? [];
  const resolved = rows.filter((r) => r.resolved);
  const unresolvedCount = rows.length - resolved.length;

  return (
    <div className="border-t border-border-1/60 pt-4 space-y-2">
      <CardLabel className="flex items-center gap-1.5">
        <Users size={11} /> Per-account assessments{resolved.length > 0 ? ` · ${resolved.length}` : ''}
      </CardLabel>

      <CompletionBanner c={completion} />

      {resolved.length === 0 ? (
        <p className="text-xs text-fg-faint leading-relaxed flex items-start gap-2">
          <TriangleAlert size={13} className="mt-0.5 shrink-0 text-fg-mute" />
          The AI did not return a per-account reading for this investigation, a large investigation can
          exceed a single response.
        </p>
      ) : (
        <div className="space-y-2">
          {resolved.map((r) => (
            <div
              key={r.external_id ?? r.ref}
              className="rounded-sm border border-border-1/60 bg-bg-elev-2/40 p-3 space-y-2"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-fg break-all">{r.handle ?? r.ref}</span>
                {r.suspicion_tier && <TierBadge tier={r.suspicion_tier} size="sm" />}
                {typeof r.omi_score === 'number' && (
                  <span className="flex items-baseline gap-1 ml-auto" title="This account's OMI score (0-100).">
                    <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">OMI</span>
                    <span className="stat-value text-base font-semibold text-fg tabular-nums">
                      {Math.max(0, Math.min(100, Math.round(r.omi_score)))}
                    </span>
                    <span className="font-mono text-2xs text-fg-mute">/100</span>
                  </span>
                )}
              </div>
              {typeof r.omi_score === 'number' && (
                <ProbabilityBar
                  value={Math.max(0, Math.min(100, Math.round(r.omi_score))) / 100}
                  tier={r.suspicion_tier}
                  size="sm"
                />
              )}
              <AccountMetadata r={r} />
              {r.assessment && (
                <p className="text-xs text-fg-dim leading-relaxed whitespace-pre-line">{r.assessment}</p>
              )}
              <SignalBreakdown signals={r.signals} confidence={r.confidence} />
              {r.citations.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {r.citations.map((c, i) => (
                    <span key={i} className="font-mono text-2xs rounded-full border border-border-1/60 text-fg-mute px-1.5 py-0.5">
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {unresolvedCount > 0 && (
            <p className="text-2xs text-fg-faint leading-relaxed">
              {unresolvedCount} per-account assessment{unresolvedCount === 1 ? '' : 's'} referenced an
              account alias that didn&apos;t resolve to a scanned commenter and {unresolvedCount === 1 ? 'was' : 'were'} omitted.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// Direction is echoed from the detector contribution (raises / lowers / neutral). Prefer the
// structured field; fall back to the column's tone only when the model omitted it.
function directionMark(
  direction: AnalystEvidenceItem['direction'],
  tone: 'raise' | 'lower',
): { sym: string; cls: string } {
  const d = direction ?? (tone === 'raise' ? 'raises' : 'lowers');
  if (d === 'raises') return { sym: '▲', cls: 'text-danger' };
  if (d === 'lowers') return { sym: '▼', cls: 'text-accent' };
  return { sym: '•', cls: 'text-fg-mute' };
}

function EvidenceList({
  label, tone, items,
}: { label: string; tone: 'raise' | 'lower'; items: AnalystEvidenceItem[] }) {
  return (
    <div>
      <CardLabel className="mb-2">{label}</CardLabel>
      {items && items.length > 0 ? (
        <ul className="space-y-2">
          {items.map((it, i) => {
            const mark = directionMark(it.direction, tone);
            return (
              <li key={i} className="text-xs text-fg-dim leading-relaxed">
                <div className="flex gap-2">
                  <span className={mark.cls}>{mark.sym}</span>
                  <span>
                    <span className="text-fg-mute font-mono">{it.signal}</span>. {it.claim}
                  </span>
                </div>
                {/* impact = the detector's share of total score movement (echoed). Shown as a bar. */}
                {typeof it.impact === 'number' && (
                  <div className="mt-1 pl-5 max-w-[180px]">
                    <ProbabilityBar value={it.impact} size="sm" />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-xs text-fg-faint">None reported.</p>
      )}
    </div>
  );
}

function PlainList({
  label, lead, items,
}: { label: string; lead?: string; items: string[] }) {
  if (!lead && (!items || items.length === 0)) return null;
  return (
    <div>
      <CardLabel className="mb-2">{label}</CardLabel>
      {lead && <p className="text-xs text-fg-dim mb-1.5 leading-relaxed">{lead}</p>}
      {items && items.length > 0 && (
        <ul className="space-y-1 list-disc pl-4">
          {items.map((s, i) => (
            <li key={i} className="text-xs text-fg-dim leading-relaxed">{s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
