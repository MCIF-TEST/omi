/**
 * Typed HTTP client for the omi FastAPI service — CLIENT-SAFE.
 *
 * Exports `apiClient` (browser-side, uses /api/* rewrite for same-origin
 * cookies) and all the shared types. No imports of `next/headers` or
 * other server-only modules — this file gets bundled into the browser.
 *
 * Server components import `apiServer` from `./api-server` (NOT this file).
 */

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

/** Shared response parser. Underscore-prefixed because the server module
 *  re-uses it; not intended as a public API. */
export async function _parse<T>(res: Response): Promise<T> {
  const text = await res.text();
  const parsed = text ? _tryJson(text) : { ok: true as const, value: undefined };
  const body = parsed.ok ? parsed.value : text;
  if (!res.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body && typeof (body as any).detail === 'string')
        ? (body as any).detail
        : res.statusText;
    throw new ApiError(res.status, detail, body);
  }
  // A 2xx response whose body arrived but doesn't parse as JSON means the
  // response was truncated or replaced by a gateway/proxy error page — common
  // when a long scan exceeds an upstream timeout and the connection is cut
  // after the status line. Silently returning the raw string here used to
  // leave callers with `data` set to an unrenderable string, so the UI showed
  // nothing at all. Surface it as an error instead.
  if (text && !parsed.ok) {
    throw new ApiError(
      res.status,
      'The server returned an incomplete response. The request may have ' +
        'timed out — try again, and reduce the batch size if it persists.',
      body,
    );
  }
  return body as T;
}

type JsonParse = { ok: true; value: unknown } | { ok: false };
function _tryJson(s: string): JsonParse {
  try { return { ok: true, value: JSON.parse(s) }; } catch { return { ok: false }; }
}

/** Browser-side fetch. Uses /api/* rewrite for same-origin cookies. */
export async function apiClient<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
    credentials: 'same-origin',
  });
  return _parse<T>(res);
}

// ---------------------------------------------------------------------------
// Shared response types (mirror app/schemas.py — kept thin until Phase 1.5
// generates types from OpenAPI directly).
// ---------------------------------------------------------------------------

export type Tier = 'low' | 'moderate' | 'elevated' | 'high';

export interface User {
  id: number;
  email: string;
  credits_remaining: number;
  subscription_status: string | null;
  subscription_renews_at: string | null;
  is_admin: boolean;
  referral_code: string | null;
  referral_credits_earned: number;
}

export interface EngineStatus {
  version: string;
  env: string;
  total_accounts: number;
  total_scans: number;
  total_engagement_edges: number;
  total_video_scans: number;
  fingerprints_stored: number;
  last_scan_at: string | null;
  youtube_configured: boolean;
  twitter_configured: boolean;
  twitter_available: boolean;
  auth_required: boolean;
  billing_configured: boolean;
  monthly_credit_grant: number;
  storage_ephemeral: boolean;
  youtube_quota_used_today: number;
  youtube_quota_daily_limit: number;
}

export interface HistoricalScan {
  scanned_at: string;
  overall_probability: number;
  confidence: number;
  tier: Tier;
  summary: string;
  reasons: string[];
  weak_signals: string[];
  signals: SignalResult[];  // populated for every scan in the history
}

export type TrendDirection = 'stable' | 'rising' | 'falling' | 'volatile' | 'insufficient';

export interface TrendInfo {
  direction: TrendDirection;
  slope: number;
  volatility: number;
  net_change: number;
  sample_size: number;
  summary: string;
}

export type RiskTier = 'low' | 'moderate' | 'high' | 'extreme';
export type CoordinationLabel =
  | 'organic'
  | 'mixed'
  | 'suspicious'
  | 'coordinated'
  | 'manipulation_network'
  | 'unscored';

// ---------------------------------------------------------------------------
// Campaigns — mirrors apps/api/app/routes/campaigns.py (CampaignSummary /
// CampaignDetail / CampaignMemberOut / CampaignObservationOut).
//
// The Campaign is the durable, evolving record of a coordinated account
// group: observations and evidence, never a verdict. ``status`` is
// 'observed' on first detection and 'recurring' once observation_count > 1.
// Discriminative methods (fingerprint_cluster / co_engagement / co_tag) carry
// a maximal verdict on their own; supporting-only campaigns (style_match /
// temporal_semantic / age_cohort) are corroboration-gated and surface as
// "supporting evidence only" in the UI.
// ---------------------------------------------------------------------------

export type CampaignStatus = 'observed' | 'recurring';

export interface CampaignSummary {
  campaign_key: string;
  name: string;
  platform: string;
  coordination_score: number;
  max_coordination_score: number;
  confidence: number;
  member_count: number;
  observation_count: number;
  methods: string[];
  hashtags: string[];
  mentions: string[];
  status: CampaignStatus;
  first_detected_at: string;
  last_seen_at: string;
  // Opt-in public sharing (null / false until shared).
  share_token: string | null;
  is_public: boolean;
}

export interface CampaignMemberOut {
  account_external_id: string;
  handle: string | null;
  times_observed: number;
  methods: string[];
}

export interface CampaignObservationOut {
  observed_at: string;
  context_id: string | null;
  coordination_score: number;
  member_count: number;
  methods: string[];
  evidence: string[];
}

export interface CampaignDetail extends CampaignSummary {
  evidence: string[];
  theme: string | null;
  members: CampaignMemberOut[];
  observations: CampaignObservationOut[];
}

export interface CampaignsResponse {
  campaigns: CampaignSummary[];
  total: number;
}

export type CampaignSort = 'recent' | 'score' | 'size' | 'recurrence';

/** Detector taxonomy — mirrors aggregate.DISCRIMINATIVE_DETECTORS exactly.
 *  Discriminative detectors can carry a maximal verdict alone; supporting
 *  detectors need corroboration (≥1 discriminative OR ≥2 distinct supporting).
 *  Used to render the "supporting evidence only" trust badge. */
export const DISCRIMINATIVE_DETECTORS: ReadonlySet<string> = new Set([
  'fingerprint_cluster',
  'co_engagement',
  'co_tag',
]);

export function isCorroborated(methods: readonly string[]): boolean {
  const distinct = new Set(methods);
  if (distinct.size >= 2) return true;
  for (const m of distinct) if (DISCRIMINATIVE_DETECTORS.has(m)) return true;
  return false;
}

// Public campaign sharing — mirrors apps/api/app/routes/campaigns.py.
export interface CampaignShareResponse {
  campaign_key: string;
  share_token: string;
  is_public: boolean;
  published_at: string | null;
  public_url: string;
}

export interface CampaignReportView {
  meta: {
    campaign_key: string;
    name: string;
    platform: string;
    status: string;
    generator: string;
    published_at: string | null;
    first_detected_at: string | null;
    last_seen_at: string | null;
  };
  verdict: {
    max_coordination_score: number;
    coordination_score: number;
    confidence: number;
    member_count: number;
    observation_count: number;
    corroborated: boolean;
    discriminative_methods: string[];
    methods: string[];
  };
  evidence_for: string[];
  evidence_against: string[];
  hashtags: string[];
  mentions: string[];
  members: CampaignMemberOut[];
  observations: CampaignObservationOut[];
  methodology: string;
  disclaimer: string;
  /** Present only on featured example reports: the other featured campaign(s)
   *  an anonymous visitor can hop to without an account. */
  other_featured?: { name: string; share_token: string }[];
}

export interface CampaignReportResponse {
  view: CampaignReportView;
}

// Founder learning (master-plan Phase 4) — mirrors apps/api/app/routes/learning.py.
export interface WtpPromptStatus {
  show_wtp: boolean;
}

// Featured campaigns — real, disclosed influence operations seeded for first-run
// value (mirrors apps/api/app/routes/campaigns.py FeaturedCampaign).
export interface FeaturedCampaign extends CampaignSummary {
  blurb: string | null;
}

export interface FeaturedCampaignsResponse {
  campaigns: FeaturedCampaign[];
}

export interface NarrativeOut {
  id: number;
  label: string;
  member_count: number;
  distinct_authors: number;
  recent_members: number;
  spread_ratio: number;
  first_seen_at: string;
  last_seen_at: string;
  sample_text: string;
  inauthenticity_score: number;
  risk_label: string;
  platforms: string[];
  // Coordination intelligence panel
  risk_tier: RiskTier;
  coordination_score: number;
  manipulation_probability: number;
  synchronization_intensity: number;
  semantic_cohesion: number;
  cluster_confidence: number;
  coordination_label: CoordinationLabel;
  qualifying_member_count: number;
  qualifying_author_count: number;
}

export interface NarrativeTopAccount {
  external_id: string;
  handle: string;
  display_name: string | null;
  platform: string;
  comment_count: number;
  tier: string | null;
  display_tier: string | null;
  distinct_parents: number;
  influence_score: number;
}

export interface NarrativeSample {
  text: string;
  account_external_id: string;
  handle: string | null;
  platform: string;
  parent_id: string | null;
  observed_at: string;
}

export interface NarrativeSignalBreakdown {
  name: string;
  value: number;
  weight: number;
}

export interface NarrativePropagationPoint {
  bucket_start: string;
  count: number;
  velocity: number;
  suspicious_count: number;
}

export interface NarrativeBurst {
  bucket_start: string;
  velocity: number;
  ratio: number;
  severity: 'moderate' | 'high' | 'extreme';
  suspicious_count: number;
}

export interface NarrativeOriginWindow {
  first_seen: string;
  suspicious_first_seen: string | null;
  lag_hours: number | null;
}

export interface NarrativeGraphNode {
  external_id: string;
  handle: string;
  platform: string;
  tier: string | null;
  display_tier: string | null;
  comment_count: number;
  distinct_parents: number;
  influence_score: number;
}

export interface NarrativeGraphEdge {
  a: string;
  b: string;
  strength: number;
  methods: string[];
}

export interface NarrativeGraph {
  nodes: NarrativeGraphNode[];
  edges: NarrativeGraphEdge[];
}

export interface NarrativeDetail {
  id: number;
  label: string;
  member_count: number;
  distinct_authors: number;
  spread_ratio: number;
  first_seen_at: string;
  last_seen_at: string;
  inauthenticity_score: number;
  risk_label: string;
  platforms: string[];
  platform_breakdown: Record<string, number>;
  activity: Array<{ date: string; count: number }>;
  top_accounts: NarrativeTopAccount[];
  samples: NarrativeSample[];
  ai_analysis: string;
  ai_provider: string;
  // Coordination intelligence panel
  risk_tier: RiskTier;
  coordination_score: number;
  manipulation_probability: number;
  synchronization_intensity: number;
  semantic_cohesion: number;
  cluster_confidence: number;
  coordination_label: CoordinationLabel;
  qualifying_member_count: number;
  qualifying_author_count: number;
  signal_breakdown: NarrativeSignalBreakdown[];
  propagation: NarrativePropagationPoint[];
  bursts: NarrativeBurst[];
  origin: NarrativeOriginWindow | null;
  graph: NarrativeGraph;
}

// ---------------------------------------------------------------------------
// Scan / investigation payload (mirrors apps/api/app/schemas.py — kept light).
// ---------------------------------------------------------------------------

export interface SignalResult {
  name: string;
  probability: number;
  confidence: number;
  evidence: string[];
  sub_signals: Record<string, number>;
  /**
   * Supplemental signals (e.g. ai_writing) are computed and shown for context
   * but excluded from the suspicion score — AI-assisted writing is not evidence
   * of inauthenticity. Render these distinctly so a high reading can't be
   * mistaken for a risk contribution.
   */
  supplemental?: boolean;
}

export interface CommenterScanResult {
  platform: string;
  external_id: string;
  handle: string;
  display_name: string | null;
  avatar_url: string | null;
  overall_probability: number;
  confidence: number;
  tier: Tier;
  summary: string;
  from_cache: boolean;
  matched_prior_neighbors: number;
  error: string | null;
  coordination_adjusted_probability: number | null;
  coordination_evidence: string[];
  suspected_intent: string | null;
  intent_label: string | null;
  reasons: string[];
  weak_signals: string[];
  score_adjustments: string[];
  recent_activity: Array<{
    text: string;
    created_at: string | null;
    parent_id: string | null;
    /** Human-readable title of the parent content, when on file. */
    parent_title?: string | null;
    like_count: number | null;
  }>;
  activity_total: number;
  signals: SignalResult[];
  /** Signed per-detector attribution: what RAISED vs LOWERED the score —
   *  including the exculpatory "community" footprint. Optional: empty on cached
   *  commenters and absent from investigations saved before this shipped. */
  contributions?: DetectorContribution[];
}

export interface DetectorContribution {
  name: string;
  headline: string;
  probability: number;
  confidence: number;
  impact: number; // share of total score movement, 0–1
  direction: 'raises' | 'lowers' | 'neutral';
  supplemental: boolean;
  evidence: string | null;
}

export interface AccountAnalysisResponse {
  platform: string;
  external_id: string;
  handle: string;
  analysis: string;
  provider: string;
}

export interface CrossLink {
  kind: string;
  severity: 'info' | 'moderate' | 'elevated' | 'high';
  summary: string;
  evidence: string[];
  related_entities: string[];
  metadata: Record<string, number>;
}

export interface CoordinationCluster {
  method: string;
  members: string[];
  score: number;
  evidence: string[];
  metadata: Record<string, number>;
}

export interface FullVideoScanResult {
  video_id: string;
  platform: string;
  commenter_count: number;
  fresh_count: number;
  cached_count: number;
  quota_used: number;
  tier_distribution: Record<string, number>;
  high_suspicion_handles: string[];
  commenters: CommenterScanResult[];
  thread_scan: {
    overall_probability: number;
    confidence: number;
    tier: Tier;
    summary: string;
  };
  // P3.1.6 — the AI-native Comment Analysis compatibility output. Present only when Comment
  // Analysis is enabled; the UI consumes this in preference to the deterministic thread_scan.
  comment_analysis?: {
    overall_probability: number;
    tier: Tier;
    comment_count: number;
    provider: string;
    model_backed: boolean;
  } | null;
  coordination_score: number;
  coordination_tier: Tier;
  clusters: CoordinationCluster[];
  next_page_token: string | null;
  summary: string;
}

export interface AccountScanOut {
  external_id: string;
  handle: string;
  display_name: string | null;
  avatar_url: string | null;
  bio: string | null;
  follower_count: number | null;
  account_created_at: string | null;
  overall_probability: number;
  confidence: number;
  tier: Tier;
  summary: string;
  from_cache: boolean;
  matched_prior_neighbors: number;
  history_size: number;
  suspected_intent: string | null;
  intent_label: string | null;
  reasons: string[];
  recent_activity: Array<{
    text: string;
    created_at: string | null;
    parent_id: string | null;
    /** Human-readable title of the parent content, when on file. */
    parent_title?: string | null;
    like_count: number | null;
  }>;
  activity_total: number;
}

export interface ComprehensiveScanResult {
  focus_account: AccountScanOut | null;
  video: FullVideoScanResult | null;
  comments_scan: any | null;
  cross_links: CrossLink[];
  convergence_score: number;
  matrix: any[];
  matrix_methods: string[];
  overall_tier: Tier;
  overall_probability: number;
  summary: string;
  inputs_provided: string[];
  quota_used: number;
  next_page_token: string | null;
  video_id: string | null;
  investigation_slug: string | null;
}

// ---------------------------------------------------------------------------
// Saved investigations
// ---------------------------------------------------------------------------

export type InvestigationVerdict =
  | 'pending'
  | 'confirmed_bot_ring'
  | 'likely_inauthentic'
  | 'mixed'
  | 'likely_authentic'
  | 'inconclusive';

export const VERDICT_LABELS: Record<InvestigationVerdict, string> = {
  pending: 'Pending',
  confirmed_bot_ring: 'Confirmed bot ring',
  likely_inauthentic: 'Likely inauthentic',
  mixed: 'Mixed',
  likely_authentic: 'Likely authentic',
  inconclusive: 'Inconclusive',
};

export interface InvestigationSummary {
  slug: string;
  label: string;
  input_url: string;
  kind: string;
  overall_probability: number;
  overall_tier: Tier;
  /** Overall confidence 0..1; null for investigations saved before it was tracked. */
  confidence: number | null;
  summary: string;
  quota_used: number;
  batch_count: number;
  created_at: string;
  updated_at: string;
  target_id: string | null;
  verdict: InvestigationVerdict | null;
}

export interface InvestigationsListResponse {
  investigations: InvestigationSummary[];
}

export interface InvestigationDetailResponse {
  slug: string;
  label: string;
  input_url: string;
  kind: string;
  overall_probability: number;
  overall_tier: Tier;
  summary: string;
  quota_used: number;
  batch_count: number;
  created_at: string;
  updated_at: string;
  payload: ComprehensiveScanResult;
  share_token: string | null;
  is_public: boolean;
  published_at: string | null;
  commentary_text: string | null;
  commentary_provider: string | null;
  commentary_generated_at: string | null;
  verdict: InvestigationVerdict | null;
  concluded_at: string | null;
  notes: string | null;
}

export interface CommentaryResponse {
  slug: string;
  text: string;
  provider: string;
  tokens_used: number;
  generated_at: string;
  cached: boolean;
}

// Omi Analyst — structured, evidence-bounded assessment of an investigation.
// Feature-flagged OFF by default; the route returns 503 when disabled, 202 while
// generating (poll again), and 200 with `assessment` when ready. `assessment`
// mirrors ml/analyst/analyst_response_schema.json.
export interface AnalystEvidenceItem {
  signal: string;
  claim: string;
  direction?: 'raises' | 'lowers' | 'neutral';
  impact?: number;
  evidence_refs?: string[];
}

// One per-domain reasoning section from the single comprehensive Mistral response. The model
// authors a short `assessment` and cites evidence ids/aliases; the six sections are views over the
// ONE inference (never separate AI calls).
export interface ComprehensiveSection {
  assessment: string;
  citations?: string[];
}

// The six per-domain reasoning sections of the comprehensive Mistral response, keyed exactly as the
// backend persists them (app.reasoning.prompts.comprehensive_investigation_template.COMPREHENSIVE_SECTION_KEYS).
export interface ComprehensiveSections {
  comment_reasoning?: ComprehensiveSection;
  commenter_history_reasoning?: ComprehensiveSection;
  account_reasoning?: ComprehensiveSection;
  narrative_reasoning?: ComprehensiveSection;
  coordination_reasoning?: ComprehensiveSection;
  campaign_reasoning?: ComprehensiveSection;
}

// One per-account reasoning row from the comprehensive response, after the backend echo-join. `ref` is
// the account alias the model cited; identity + engine numbers are joined server-side (echo discipline).
export interface CommenterAssessment {
  ref: string;
  // AI-first: the per-account OMI score (0-100) + tier are the MODEL's, reasoned from this account's
  // own evidence. `handle`/`external_id` are identity (from metadata); `engine_probability` is a
  // secondary reference, never the account's score.
  omi_score?: number;
  suspicion_tier?: Tier;
  assessment: string;
  citations: string[];
  resolved: boolean;
  handle?: string;
  external_id?: string;
  engine_probability?: number;
  /** @deprecated legacy engine field — replaced by omi_score + engine_probability */
  suspicion_probability?: number;
}

// Full-investigation completion status (Phase 5H): whether the AI reasoned over every commenter, and if
// not, why + how much remains. Backend-computed (never model-generated); surfaced so the user always
// knows whether the investigation is complete. `incomplete_kind`: truncated_output | missing_assessments
// | omitted_input | null.
export interface CompletionStatus {
  complete: boolean;
  finish_reason: string | null;
  stopped_on_token_limit: boolean;
  json_complete: boolean;
  schema_valid: boolean;
  governor_valid: boolean;
  represented_commenters: number;   // expected (shown to the model)
  assessed_commenters: number;      // returned (actually assessed)
  missing_commenters: number;
  omitted_input_commenters: number;
  max_output_tokens: number | null; // completion budget requested
  output_tokens: number | null;     // actual completion size
  incomplete_kind: 'truncated_output' | 'missing_assessments' | 'omitted_input' | null;
  reason: string;
  estimated_remaining_commenters: number;
}

export interface AnalystAssessment {
  verdict: string;
  /** THE OMI SCORE — the analyst's single composite authenticity-risk score, 0–100 (higher = stronger
   *  evidence of inauthentic/coordinated behavior). The only investigation score. */
  omi_score: number;
  suspicion_tier: string;
  /** DEPRECATED — the legacy 0–1 inauthenticity probability. Superseded by omi_score; may be absent. */
  suspicion_probability?: number;
  confidence_band: string;
  confidence_rationale: string;
  headline: string;
  assessment: string;
  evidence_for: AnalystEvidenceItem[];
  evidence_against: AnalystEvidenceItem[];
  uncertainty: string[];
  what_would_change_this: string[];
  limits_statement: string;
  coordination_label?: string | null;
  legitimate_hypothesis?: string | null;
  supplemental_context?: { signal: string; note: string }[];
  // The engine's corroboration state, echoed onto the assessment (overlaid from the deterministic
  // Floor, never model-fabricated — apps/api runtime.py). It bounds the coordination read: a maximal
  // 'coordinated' verdict requires >=1 discriminative method AND single_axis_capped === false.
  corroboration?: {
    discriminative_methods: string[];
    single_axis_capped: boolean;
    convergence: boolean;
  };
  governance?: {
    verdict?: string;
    provider?: string;
    latency_ms?: number;
    model_revision?: string | null;
    trace_id?: string;
  };
  // Per-account (per-commenter) reasoning from the ONE comprehensive response: the model authors the
  // `assessment` + `citations` keyed by an account alias; OmiSphere echo-joins the real identity
  // (`handle`, `external_id`) and the engine's `suspicion_tier`/`suspicion_probability` (never
  // model-fabricated). `resolved` is false when the model cited an alias that didn't map to a known
  // commenter — surfaced with a flag, never dropped. Empty/absent when the model produced none.
  commenter_assessments?: CommenterAssessment[];
  // Full-investigation completion status (Phase 5H): whether every commenter received AI reasoning.
  completion?: CompletionStatus;
  // The six domain-reasoning sections of the single comprehensive Mistral response (present when the
  // comprehensive path produced them). Rendered as views over ONE inference — never fetched per panel.
  comprehensive_sections?: ComprehensiveSections;
  // Structural + citation-resolution report for the six domain sidecars (apps/api
  // governor/comprehensive.py:validate_comprehensive_sections). Per-section `resolved`/`unresolved`
  // let the panel mark citations that don't resolve against the evidence universe.
  comprehensive_validation?: {
    structurally_valid?: boolean;
    unresolved_total?: number;
    citation_universe_size?: number;
    missing_sections?: string[];
    sections?: Record<string, {
      present: boolean;
      shape_ok: boolean;
      expected_shape?: string;
      citation_count: number;
      resolved: string[];
      unresolved: string[];
    }>;
  };
  // Forensic + production-verification trace for the ONE inference. `model_backed` gates whether the
  // model authored this assessment (true) or the deterministic Floor stood in (false); the UI must
  // never present Floor prose as AI reasoning — it keys off this. The remaining fields power the
  // dev-only Production Verification panel (Phase 5C): they prove which gateway/model served the
  // investigation, whether validation passed, and the latency/token/cost of the call. No secrets.
  investigation_trace?: {
    model_backed?: boolean;
    inference_count?: number;
    endpoint_called?: boolean;
    evidence_coverage_mode?: string;
    evidence_represented_accounts?: number | null;
    evidence_omitted_accounts?: number | null;
    // transport / model provenance
    provider?: string;                    // "openrouter" | "huggingface"
    requested_model?: string | null;      // e.g. "@preset/omi-master-v1"
    served_model?: string | null;         // the model the gateway actually ran, e.g. "openai/gpt-5-mini"
    openrouter_preset?: string | null;    // "omi-master-v1"
    master_prompt_version?: string | null;
    master_prompt_hash?: string | null;   // "map:…" — what Omi expects the preset to contain
    canonical_schema_id?: string | null;
    // pipeline-stage flags
    request_completed?: boolean;
    json_received?: boolean;
    validation_passed?: boolean;
    fallback_reason?: string | null;
    governor_verdict?: string | null;
    comprehensive_structurally_valid?: boolean;
    canonical_validation_errors?: string[] | null;  // why a 200 model response failed schema → Floor
    // call metrics (authoritative gateway usage)
    endpoint_request_id?: string | null;  // OpenRouter generation id
    endpoint_latency_ms?: number | null;
    endpoint_cost_usd?: number | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
    response_status?: number | null;
    endpoint_error?: string | null;
    // Phase 5H — full-investigation completion (also on `completion`, mirrored here for the trace panel)
    finish_reason?: string | null;
    max_output_tokens?: number | null;
    commenters_total?: number | null;
    commenters_assessed?: number | null;
    completion_complete?: boolean;
    completion_incomplete_kind?: string | null;
  };
}

export interface AnalystResponse {
  slug: string;
  enabled: boolean;
  status: 'ready' | 'generating';
  cached: boolean;
  assessment: AnalystAssessment | null;
  provider?: string | null;
  generated_at?: string | null;
}

// Monitoring + watchlists (Phase 8) ------------------------------------------

export interface AlertOut {
  id: number;
  user_id: number | null;
  watchlist_id: number | null;
  kind: string;
  severity: 'info' | 'moderate' | 'elevated' | 'high';
  message: string;
  payload: Record<string, any>;
  created_at: string;
  read_at: string | null;
}

export interface AlertsResponse {
  alerts: AlertOut[];
  unread_count: number;
}

export interface FeedResponse {
  items: AlertOut[];
}

export interface WatchlistOut {
  id: number;
  kind: string;
  target_id: string;
  platform: string;
  label: string;
  alert_threshold_tier: string;
  last_seen_tier: string | null;
  last_seen_probability: number | null;
  last_checked_at: string | null;
  last_alert_at: string | null;
  created_at: string;
}

export interface WatchlistsResponse {
  watchlists: WatchlistOut[];
}

// ---------------------------------------------------------------------------
// Reports (Phase 6)
// ---------------------------------------------------------------------------

export interface ShareResponse {
  slug: string;
  share_token: string;
  is_public: boolean;
  published_at: string | null;
  public_url: string;
}

export interface ReportMeta {
  template: 'executive' | 'evidence';
  slug: string;
  label: string;
  input_url: string;
  kind: string;
  created_at: string | null;
  published_at: string | null;
  batch_count: number;
  quota_used: number;
}

export interface ReportVerdict {
  overall_probability: number;
  overall_tier: Tier;
  summary: string;
  convergence_score: number;
}

export interface ReportCommenter {
  handle: string;
  external_id: string;
  tier: Tier;
  overall_probability: number;
  intent_label: string | null;
  summary: string | null;
  reasons: string[];
  recent_activity: Array<{
    text: string;
    created_at: string | null;
    parent_id: string | null;
    /** Human-readable title of the parent content, when on file. */
    parent_title?: string | null;
    like_count: number | null;
  }>;
}

export interface ReportView {
  meta: ReportMeta;
  verdict: ReportVerdict;
  inputs_provided: string[];
  headline_cross_link: any | null;
  cross_links: any[];
  focus_account: any | null;
  top_flagged: ReportCommenter[];
  total_flagged: number;
  video: any | null;
  methodology: string;
  stats: Record<string, string | number>;
}

export interface PublicReportResponse {
  view: ReportView;
}

export interface GraphNode {
  external_id: string;
  handle: string;
  display_name: string | null;
  tier: Tier | null;
  last_score: number | null;
  community_id: number;
}

export interface GraphEdge {
  a: string;
  b: string;
  strength: number;
}

export interface AccountSubgraphResponse {
  focal: string;
  depth: number;
  nodes: GraphNode[];
  edges: GraphEdge[];
  community_count: number;
}

export interface CommunitySampleAccount {
  external_id: string;
  handle: string;
  tier: Tier | null;
}

export interface CommunityOut {
  id: number;
  size: number;
  avg_strength: number;
  max_strength: number;
  methods_seen: string[];
  sample_accounts: CommunitySampleAccount[];
  total_members: number;
}

export interface CommunitiesResponse {
  platform: string;
  min_size: number;
  communities: CommunityOut[];
}

// User-curated named graphs — /v1/graphs/*
export interface UserGraphMemberOut {
  id: number;
  external_id: string;
  platform: string;
  handle: string;
  display_name: string | null;
  tier: Tier | null;
  avatar_url: string | null;
  added_at: string;
}

export interface UserGraphOut {
  id: number;
  name: string;
  platform: string;
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface UserGraphDetail extends UserGraphOut {
  members: UserGraphMemberOut[];
  edges: GraphEdge[];
}

export interface NarrativesResponse {
  window_days: number;
  embedder: string;
  narratives: NarrativeOut[];
}

export interface AccountHistoryResponse {
  platform: string;
  external_id: string;
  handle: string;
  display_name: string | null;
  bio: string | null;
  follower_count: number | null;
  account_created_at: string | null;
  first_seen_at: string | null;
  last_scanned_at: string | null;
  scans: HistoricalScan[];
  total_scans: number;
  trend: TrendInfo;
}

// ---------------------------------------------------------------------------
// Phase 10 — Content Intelligence types
// ---------------------------------------------------------------------------

export interface ContentEntitySummary {
  id: number;
  platform: string;
  content_id: string;
  kind: string;
  title: string | null;
  author_external_id: string | null;
  author_handle: string | null;
  canonical_url: string | null;
  thumbnail_url: string | null;
  total_batches: number;
  total_comments_collected: number;
  total_distinct_authors: number;
  contributor_count: number;
  latest_coordination_score: number;
  latest_risk_tier: string;
  latest_tier_distribution: Record<string, number>;
  reply_pod_count: number;
  first_scanned_at: string;
  last_scanned_at: string;
}

export interface CommentBatchOut {
  id: number;
  fetched_at: string;
  comments_fetched: number;
  new_comments: number;
  duplicates: number;
  distinct_authors: number;
  new_authors: number;
  coordination_score: number;
  risk_tier: string;
  tier_distribution: Record<string, number>;
  summary: string | null;
  has_more: boolean;
}

export interface ContentCommentOut {
  id: number;
  external_comment_id: string;
  author_external_id: string;
  author_handle: string | null;
  text: string;
  like_count: number | null;
  reply_count: number | null;
  observed_at: string;
  first_batch_id: number;
}

export interface ContentEntityDetail {
  entity: ContentEntitySummary;
  batches: CommentBatchOut[];
  recent_comments: ContentCommentOut[];
  total_comments: number;
  has_continuation: boolean;
}

export interface ContentEntityListResponse {
  total: number;
  platform: string | null;
  entities: ContentEntitySummary[];
}

export interface AuthorContentRow {
  entity: ContentEntitySummary;
  comment_count: number;
  first_comment: string;
  last_comment: string;
  sample_text: string;
}

export interface NotificationPrefs {
  email_enabled: boolean;
  webhook_enabled: boolean;
  webhook_url: string | null;
  email: string;
}

export interface AuthorCommentRow {
  comment: ContentCommentOut;
  entity: ContentEntitySummary;
}

export interface AuthorCommentsResponse {
  platform: string;
  author_external_id: string;
  author_handle: string | null;
  total: number;
  comments: AuthorCommentRow[];
}

export interface BatchDiffResponse {
  from_batch: CommentBatchOut;
  to_batch: CommentBatchOut;
  coordination_score_delta: number;
  risk_tier_changed: boolean;
  tier_distribution_delta: Record<string, number>;
  new_comment_count: number;
  new_author_count: number;
  new_authors: string[];
  sample_new_comments: ContentCommentOut[];
}

export interface AuthorPresenceResponse {
  platform: string;
  author_external_id: string;
  author_handle: string | null;
  total_comments: number;
  content_count: number;
  first_seen: string | null;
  last_seen: string | null;
  entities: AuthorContentRow[];
}

// ---------------------------------------------------------------------------
// Phase 12 — Ground-truth labels
// ---------------------------------------------------------------------------

export const LABEL_KINDS = [
  'bot',
  'human',
  'unclear',
  'commercial_spam',
  'political_coord',
  'engagement_farm',
  'ai_content',
  'suspended',
] as const;
export type LabelKind = typeof LABEL_KINDS[number];

export const LABEL_CONFIDENCES = ['high', 'medium'] as const;
export type LabelConfidence = typeof LABEL_CONFIDENCES[number];

export const LABEL_TIERS = ['low', 'moderate', 'elevated', 'high'] as const;

export interface AccountLabel {
  id: number;
  account_id: number;
  user_id: number | null;
  user_email: string | null;
  platform: string;
  external_id: string;
  handle: string | null;
  label: LabelKind;
  expected_tier: 'low' | 'moderate' | 'elevated' | 'high';
  confidence: LabelConfidence;
  source: 'manual' | 'youtube_suspension' | 'imported_dataset';
  rationale: string | null;
  created_at: string;
}

export interface AccountLabelsResponse {
  total: number;
  labels: AccountLabel[];
  by_label: Record<string, number>;
  by_source: Record<string, number>;
}

export interface CalibrationEvaluation {
  n_cases: number;
  tier_accuracy?: number;
  brier_score?: number;
  macro_f1?: number;
  per_tier?: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  per_label_accuracy?: Record<string, number>;
  per_source_accuracy?: Record<string, number>;
  message?: string;
}

// ---------------------------------------------------------------------------
// Engine benchmark scoreboards  (/v1/intelligence/benchmark*)
// The synthetic, CI-gated counterpart to the real-label CalibrationEvaluation:
// how good the engine is on curated benchmarks, surfaced in-product.
// ---------------------------------------------------------------------------

export interface SeedBenchmarkReport {
  benchmark_version: string;
  n_cases: number;
  brier_score: number;
  tier_accuracy: number;
  macro_f1: number;
  majority_class_rate: number;
}

export interface CoordinationBenchmarkReport {
  benchmark_version: string;
  n_scenarios: number;
  n_with_planted: number;
  n_clean: number;
  cluster_recall: number;
  member_precision: number;
  member_recall: number;
  clean_pass_rate: number;
}

export interface RescueBenchmarkReport {
  benchmark_version: string;
  n_accounts: number;
  n_bots: number;
  n_organic: number;
  standalone_bot_recall: number;
  adjusted_bot_recall: number;
  recall_lift: number;
  rescue_rate: number;
  n_rescuable: number;
  n_rescued: number;
  mean_prob_lift: number;
  organic_false_lift: number;
}

export interface MemoryCurvePoint {
  store_size: number;
  memory_confidence: number;
  adjusted_probability: number;
  adjusted_tier: Tier;
}

export interface MemoryScenarioReport {
  label: string;
  neighborhood: 'bad' | 'good' | 'distant';
  role: 'bot' | 'organic';
  standalone_tier: Tier;
  standalone_probability: number;
  learning_curve: MemoryCurvePoint[];
  warm_flagged: boolean;
  monotonic: boolean;
}

export interface MemoryBenchmarkReport {
  benchmark_version: string;
  n_scenarios: number;
  n_bad: number;
  n_good: number;
  n_distant: number;
  store_sizes: number[];
  cold_bad_recall: number;
  warm_bad_recall: number;
  memory_recall_lift: number;
  bad_monotonic_rate: number;
  mean_warm_prob_lift: number;
  good_false_lift: number;
  distant_inert_rate: number;
  per_scenario: MemoryScenarioReport[];
}

// Learned (ML) scorer status — /v1/intelligence/ml-status (admin)
export interface MlScorerStatus {
  active: boolean;
  enabled_flag: boolean;
  library_available: boolean;
  model_path_configured: boolean;
  model_loaded: boolean;
  expected_feature_schema: number;
  loaded_feature_schema: number | null;
  model_kind: string | null;
  text_head_configured: boolean;
  blend_weight: number;
  metrics: Record<string, unknown>;
  reason: string;
}

// ---------------------------------------------------------------------------
// Cross-scan account search  (/v1/accounts/search)
// ---------------------------------------------------------------------------

export interface AccountSearchResult {
  external_id: string;
  platform: string;
  handle: string;
  display_name: string | null;
  tier: Tier | null;
  overall_probability: number | null;
  last_scanned_at: string | null;
  first_seen_at: string | null;
  follower_count: number | null;
}

export interface AccountSearchResponse {
  query: string;
  platform: string;
  results: AccountSearchResult[];
}

// ---------------------------------------------------------------------------
// Activity log  (/v1/activity)
// ---------------------------------------------------------------------------

export interface ActivityEntry {
  id: number;
  created_at: string;
  platform: string;
  scan_type: string;
  credits_cost: number;
  target_input: string | null;
  success: boolean;
  refunded: boolean;
}

export interface ActivityLogResponse {
  entries: ActivityEntry[];
  total: number;
  limit: number;
  offset: number;
  credits_spent_total: number;
  credits_refunded_total: number;
}

// ---------------------------------------------------------------------------
// Bulk scan queue  (/v1/scan/bulk)
// ---------------------------------------------------------------------------

export interface BulkScanJobResult {
  url: string;
  status: 'pending' | 'running' | 'ok' | 'failed';
  slug: string | null;
  tier: Tier | null;
  probability: number | null;
  error: string | null;
}

export interface BulkScanJobSummary {
  job_id: string;
  status: 'queued' | 'running' | 'done' | 'failed';
  total: number;
  completed: number;
  failed_count: number;
  credits_estimate: number;
  credits_used: number;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface BulkScanJobResponse {
  job: BulkScanJobSummary;
  results: BulkScanJobResult[];
}

export interface BulkScanJobsListResponse {
  jobs: BulkScanJobSummary[];
}

// ---------------------------------------------------------------------------
// Channel-level deep intelligence  (/v1/channels/{platform}/{id}/intelligence)
// ---------------------------------------------------------------------------

export interface ChannelVideoSummary {
  content_id: string;
  title: string | null;
  canonical_url: string | null;
  thumbnail_url: string | null;
  total_batches: number;
  total_comments_collected: number;
  total_distinct_authors: number;
  latest_coordination_score: number;
  latest_risk_tier: string;
  latest_tier_distribution: Record<string, number>;
  first_scanned_at: string;
  last_scanned_at: string;
}

export interface ChannelRiskPoint {
  content_id: string;
  date: string;
  coordination_score: number;
  risk_tier: string;
  comment_count: number;
}

export interface ChannelTopCommenter {
  external_id: string;
  platform: string;
  handle: string;
  video_count: number;
  tier: string | null;
  overall_probability: number | null;
}

export interface ChannelAudienceComposition {
  high: number;
  elevated: number;
  moderate: number;
  low: number;
  total_commenters: number;
}

// ---------------------------------------------------------------------------
// Phase C — Reply tree + engagement pods
// ---------------------------------------------------------------------------

export interface ReplyTreeNode {
  comment_id: string;
  parent_comment_id: string | null;
  author_external_id: string;
  author_handle: string | null;
  author_tier: string | null;
  text: string;
  like_count: number | null;
  reply_count: number | null;
  posted_at: string;
  replies: ReplyTreeNode[];
  pod_id: number | null;
}

export interface ReplyTreeResponse {
  platform: string;
  content_id: string;
  total_comments: number;
  top_level_count: number;
  reply_count: number;
  roots: ReplyTreeNode[];
}

export interface ReplyPodMember {
  external_id: string;
  handle: string | null;
  tier: string | null;
  overall_probability: number | null;
}

export interface ReplyPodOut {
  pod_id: number;
  score: number;
  members: ReplyPodMember[];
  evidence: string[];
  interaction_count: number;
}

export interface ReplyPodsResponse {
  platform: string;
  content_id: string;
  pod_count: number;
  pods: ReplyPodOut[];
}

export interface ChannelIntelligenceResponse {
  platform: string;
  external_id: string;
  handle: string;
  display_name: string | null;
  bio: string | null;
  follower_count: number | null;
  first_seen_at: string | null;
  last_scanned_at: string | null;
  video_count: number;
  videos: ChannelVideoSummary[];
  audience_composition: ChannelAudienceComposition;
  risk_trend: ChannelRiskPoint[];
  top_commenters: ChannelTopCommenter[];
  avg_comments_per_video: number;
  returning_commenter_ratio: number;
}

// ---------------------------------------------------------------------------
// OmiScore intelligence layer  (/v1/intelligence/*)
// Mirrors app/intelligence/schemas.py. The flat 0–100 fields are the stable
// public contract; `dimensions` is the explainability layer.
// ---------------------------------------------------------------------------

export type RiskLevel = 'low' | 'medium' | 'high';

export interface DimensionContribution {
  detector: string;
  label: string;
  /** Detector probability AFTER any inversion the dimension applies (0–1). */
  contribution_probability: number;
  confidence: number;
  /** Share of the dimension this detector accounted for, 0–1. */
  weight_share: number;
  evidence: string[];
}

export interface IntelligenceDimension {
  key: string;
  label: string;
  description: string;
  /** 0–100 in the dimension's own direction. */
  score: number;
  confidence: number;
  is_risk: boolean;
  /**
   * Contextual dimensions (e.g. AI-generated content) are reported for
   * information but excluded from the composite risk score — AI-assisted
   * writing is not by itself a sign of inauthenticity. Render distinctly.
   */
  is_contextual?: boolean;
  contributions: DimensionContribution[];
}

export interface OmiScore {
  schema_version: number;
  // Flat public contract (all 0–100)
  omi_score: number;
  authenticity_score: number;
  coordination_probability: number;
  amplification_probability: number;
  spam_probability: number;
  ai_generation_probability: number;
  risk_level: RiskLevel;
  // Explainability
  confidence: number;
  subject: string | null;
  headline: string;
  /** Key of the highest-scoring threat dimension, if any concerning. */
  primary_threat: string | null;
  dimensions: IntelligenceDimension[];
  top_evidence: string[];
}

/**
 * The threat dimension keys that actually contribute to the composite risk
 * score, in canonical display order. Two dimensions are deliberately NOT here
 * (see CONTEXT_KEYS): AI generation (AI-assisted writing is not evidence of
 * inauthenticity) and amplification (a behavioral proxy with no reach data —
 * counting it would overclaim and double-count coordination). Both inform
 * without raising risk. Mirrors the backend's is_contextual classification.
 */
export const THREAT_KEYS = [
  'coordination_probability',
  'spam_probability',
] as const;
export type ThreatKey = (typeof THREAT_KEYS)[number];

/** Contextual dimensions: reported for information, excluded from the risk score. */
export const CONTEXT_KEYS = [
  'amplification_probability',
  'ai_generation_probability',
] as const;
export type ContextKey = (typeof CONTEXT_KEYS)[number];

export const THREAT_META: Record<ThreatKey | ContextKey, { label: string; short: string; caveat?: string }> = {
  coordination_probability:  { label: 'Coordinated activity',   short: 'Coordination' },
  // Honesty: amplification is a BEHAVIORAL proxy (re-weighted coordination /
  // engagement / timing), not measured reach — like/view/follower-velocity data
  // is not yet ingested. Surface that plainly rather than overclaiming
  // "artificial amplification" the engine cannot actually evidence.
  amplification_probability: {
    label: 'Amplification (behavioral proxy)',
    short: 'Amplification',
    caveat: 'Behavioral proxy — inferred from coordination, engagement and timing, not measured reach (likes / views / follower velocity are not yet ingested). Read as a behavioral signal, not confirmed reach inflation.',
  },
  spam_probability:          { label: 'Spam behavior',          short: 'Spam' },
  ai_generation_probability: { label: 'AI-generated content',   short: 'AI generation' },
};
