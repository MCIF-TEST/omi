'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, ShieldCheck, TriangleAlert, Users } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { AnalystLoading } from './analyst-loading';
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
// re-run), and while a generation is still in flight — the one scheduled at scan time, or the
// backend's one-shot auto-heal of an inconclusive/floored result — we hold the loading screen and
// poll until it lands. We never force a re-run from here. ~520s of polling matches the server's
// 500s generation timeout, so the wait ends when the real result does.
const MAX_POLLS = 210;

// Dev-only Production Verification Mode (Phase 5C). OFF for normal users; enabled on demand with the
// URL query `?verify=1` (or `?debug=1`), or always-on where the deploy sets NEXT_PUBLIC_OMI_VERIFY_MODE=1.
// Purely a read-only diagnostic surface over the existing forensic trace — it changes no data.
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
 * recomputes a score. Off by default — the disabled state degrades gracefully.
 */
export function AnalystPanel({ slug }: { slug: string }) {
  const [assessment, setAssessment] = useState<AnalystAssessment | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [disabled, setDisabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const startRef = useRef<number>(0);

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
    let polls = 0;

    const step = async (doRefresh: boolean): Promise<void> => {
      try {
        const r = await post(doRefresh);
        // A SAVED assessment (model-backed, or the deterministic floor) is the previous result — show
        // it as-is. We never force a re-run on open; the backend alone decides when an inconclusive
        // (floored) result is worth regenerating, and does so exactly once, returning 202 while it runs.
        if (r.status === 'ready' && r.assessment) {
          setAssessment(r.assessment);
          setProvider(r.provider ?? null);
          setGeneratedAt(r.generated_at ?? null);
          setPending(false);
          return;
        }
        // 202 generating — a scan-time generation or the backend's one-shot auto-heal is in flight.
        // Hold the loading screen and poll until it lands.
        if (polls++ >= MAX_POLLS) {
          setError('The AI analysis is taking longer than usual. It keeps running on the server — reload in a moment to pick it up.');
          setPending(false);
          return;
        }
        pollRef.current = setTimeout(() => { void step(false); }, POLL_INTERVAL_MS);
      } catch (e) {
        if (e instanceof ApiError && e.status === 503) {
          setDisabled(true);
        } else {
          setError(e instanceof ApiError ? e.message : 'Failed to generate the assessment.');
        }
        setPending(false);
      }
    };

    await step(refresh);
  };

  // Auto-load on mount: the analyst now runs server-side for every investigation
  // (scheduled at scan time), so surface its cached assessment automatically — the AI
  // reading is part of the report, not a manual action. A cached result returns
  // immediately (no new model call); 503 degrades to the graceful "not enabled" notice.
  useEffect(() => {
    void run(false);
    // Fire once per investigation; `run` is stable for the component's lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  return (
    <Card>
      <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
        <CardLabel className="m-0 flex items-center gap-1.5">
          <Brain size={11} /> Omi Analyst assessment
        </CardLabel>
        {provider && (
          <span
            className="font-mono text-2xs tracking-wider uppercase text-accent"
            title={`Generated by ${provider}`}
          >
            ▸ {provider.replace(/->fallback:.*/, ' → fallback').replace(/-v1$/, '')}
          </span>
        )}
      </div>

      {disabled ? (
        <p className="text-sm text-fg-dim flex items-start gap-2">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-fg-mute" />
          Omi Analyst reasoning isn&apos;t enabled on this server yet. The structured,
          evidence-bounded assessment becomes available once the reasoning layer is
          turned on — the investigation evidence above is unaffected.
        </p>
      ) : pending ? (
        // The analyst runs automatically for every investigation. Hold a real loading screen while
        // the OpenRouter response is on its way — it fills in the moment the result lands.
        <AnalystLoading elapsedSec={elapsedSec} />
      ) : !assessment ? (
        <p className="text-sm text-fg-dim flex items-start gap-2">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-fg-mute" />
          The Omi Analyst’s structured reading of this investigation will appear here. It interprets
          the evidence the engine already produced; it never recomputes a score.
        </p>
      ) : (
        <AssessmentView a={assessment} slug={slug} />
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

function verdictLabel(v: string): string {
  return (VERDICT_LABELS as Record<string, string>)[v] ?? v;
}

// The corroboration methods, and which of them are DISCRIMINATIVE of coordination (a maximal
// 'coordinated' read requires >=1 discriminative method AND single_axis_capped === false). Mirrors
// the backend gate — surfaced here so the panel shows WHY a coordinated read is (or isn't) permitted.
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

// The engine's corroboration state (echoed onto the assessment). Rendered as structured chips — the
// discriminative methods that fired, plus the single-axis-cap and convergence flags — so the reader
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

// Supplemental signals (e.g. AI-writing) — reported as neutral context that carries ZERO suspicion
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
              <span className="text-fg-mute font-mono">{it.signal}</span> — {it.note}
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

// Whether the AI (OpenRouter) actually authored this assessment. Prefer the explicit trace flag; fall back to the
// governance provider string for assessments persisted before the trace existed. When false, the
// synthesis prose is the deterministic Floor's — it must NEVER be shown as AI reasoning.
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
  return typeof v === 'number' ? `${Math.round(v)} ms` : '—';
}
function fmtCost(v?: number | null): string {
  return typeof v === 'number' ? `$${v.toFixed(6)}` : '—';
}
function yn(v: boolean | undefined | null): string {
  return v === true ? 'yes' : v === false ? 'no' : '—';
}

function VerificationPanel({
  a, provider, generatedAt,
}: { a: AnalystAssessment; provider: string | null; generatedAt: string | null }) {
  const t = a.investigation_trace ?? {};
  const c = a.completion;
  const aiBacked = t.model_backed === true;
  const isOpenRouter = (t.provider ?? '').toLowerCase() === 'openrouter'
    || /openrouter/i.test(provider ?? '');
  const rows: [string, React.ReactNode][] = [
    ['Provider', t.provider ?? provider ?? '—'],
    ['Served model', t.served_model ?? t.requested_model ?? '—'],
    ['Served model verified', t.served_model_verified == null
      ? '—'
      : t.served_model_verified
        ? `yes — ${t.served_model_expected ?? 'expected model'}`
        : `NO — expected ${t.served_model_expected ?? '?'}, served ${t.served_model ?? '?'}`],
    ['Preset', t.openrouter_preset ?? '—'],
    ['Protocol version', t.master_prompt_version ?? '—'],
    ['Protocol hash', t.master_prompt_hash ?? '—'],
    ['Schema id / version', `${t.canonical_schema_id ?? '—'} / v${(a as { schema_version?: number }).schema_version ?? '—'}`],
    ['Model-backed', yn(t.model_backed)],
    ['Request completed', yn(t.request_completed)],
    ['JSON received', yn(t.json_received)],
    ['Validation passed', yn(t.validation_passed)],
    ['Governor verdict', t.governor_verdict ?? '—'],
    ['Fallback used', yn(!aiBacked)],
    ['Fallback reason', t.fallback_reason ?? '—'],
    ['Latency', fmtMs(t.endpoint_latency_ms)],
    ['Input tokens', t.input_tokens ?? '—'],
    ['Output tokens', t.output_tokens ?? '—'],
    ['Total tokens', t.total_tokens ?? '—'],
    ['Estimated cost', fmtCost(t.endpoint_cost_usd)],
    ['OpenRouter request id', t.endpoint_request_id ?? '—'],
    ['HTTP status', t.response_status ?? '—'],
    ['Endpoint error', t.endpoint_error ?? '—'],
    ['Generated at', generatedAt ?? '—'],
    // Phase 5H — full-investigation completion certification
    ['— completion —', ''],
    ['Completion', c ? (c.complete ? 'complete' : `incomplete: ${c.incomplete_kind ?? '—'}`) : '—'],
    ['Commenters analyzed / expected',
      c ? `${c.assessed_commenters} / ${c.represented_commenters + c.omitted_input_commenters}` : '—'],
    ['Stopped on token limit', yn(c?.stopped_on_token_limit)],
    ['JSON complete', yn(c?.json_complete)],
    ['Schema valid', yn(c?.schema_valid)],
    ['Governor valid', yn(c?.governor_valid)],
    ['Completion budget', c?.max_output_tokens ?? t.max_output_tokens ?? '—'],
    ['Actual output size', c?.output_tokens ?? '—'],
    ['Est. remaining commenters', c?.estimated_remaining_commenters ?? '—'],
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
              ? `🟢 AI Investigation (${isOpenRouter ? 'OpenRouter' : (t.provider ?? 'model')})`
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

// THE OMI SCORE — the single composite authenticity-risk score (0–100), the investigation's headline
// figure. Higher = stronger evidence of inauthentic/coordinated behavior. Rendered as the number plus a
// tier-colored bar (score/100). This is the only investigation score; the legacy inauthenticity
// probability is retired.
function OmiScore({ score, tier }: { score: number; tier: Tier }) {
  const s = Math.max(0, Math.min(100, Math.round(score ?? 0)));
  return (
    <div className="flex items-center gap-3">
      <div className="flex items-baseline gap-1 shrink-0" title="OMI score — composite authenticity-risk, 0–100.">
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute mr-1">OMI</span>
        <span className="stat-value text-2xl font-semibold text-fg tabular-nums">{s}</span>
        <span className="font-mono text-2xs text-fg-mute">/100</span>
      </div>
      <ProbabilityBar value={s / 100} tier={tier} className="flex-1" showLabel={false} />
    </div>
  );
}

function AssessmentView({ a, slug }: { a: AnalystAssessment; slug: string }) {
  // Product-cutover rule: only AI-authored (OpenRouter) assessments render as AI reasoning. If the model
  // was not reached, the deterministic Floor stood in — we must NOT present its synthesized verdict /
  // headline / assessment / evidence as though the AI wrote it.
  if (!isModelBacked(a)) return <AiUnavailable a={a} />;

  return (
    <div className="space-y-5">
      {/* ── LEAD INVESTIGATOR SYNTHESIS (Omi Analyst · OpenRouter) ─────────── */}
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

        {/* THE OMI SCORE — the analyst's single composite authenticity-risk score (0–100), the headline
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

// The AI analysis couldn't be produced for this investigation (rare — the pipeline auto-retries a fresh
// model call once). Users see a clean, friendly notice; the technical forensic diagnostic is shown ONLY
// in dev/verification mode. We never present the deterministic Floor's synthesis as if the AI wrote it.
function AiUnavailable({ a }: { a: AnalystAssessment }) {
  const t = a.investigation_trace ?? {};
  const verbose = verificationEnabled();
  return (
    <div className="text-sm text-fg-dim flex items-start gap-2">
      <TriangleAlert size={14} className="mt-0.5 shrink-0 text-fg-mute" />
      <span>
        The AI analysis for this investigation isn’t ready yet. It runs automatically — please check back
        in a moment or scan again shortly.
        {verbose && <AiUnavailableDiagnostics t={t} governanceProvider={a.governance?.provider} />}
      </span>
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
    ['provider', t.provider ?? governanceProvider ?? '—'],
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
// pure view over the already-loaded assessment — expanding a panel triggers NO request (no per-panel
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
// model's per-account reasoning with the engine's echoed tier/probability (joined server-side — the model
// never emits a per-account number). When the model produced none, an honest empty state is shown instead
// of any deterministic fallback. `resolved: false` items (alias didn't map to a known commenter) are
// summarized as a count rather than shown as fabricated identities.
// Completion statistics — always shown so the user knows the AI coverage of THIS investigation
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

// Compact raw-metadata line for one account — the objective facts (followers, age, posts) the AI
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
          The AI did not return a per-account reading for this investigation — a large investigation can
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
                  <span className="flex items-baseline gap-1 ml-auto" title="This account's OMI score (0–100).">
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
                    <span className="text-fg-mute font-mono">{it.signal}</span> — {it.claim}
                  </span>
                </div>
                {/* impact = the detector's share of total score movement (echoed) — shown as a bar. */}
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
