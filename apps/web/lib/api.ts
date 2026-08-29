/**
 * Typed HTTP client for the omi FastAPI service. CLIENT-SAFE.
 *
 * Exports `apiClient` (browser-side, uses /api/* rewrite for same-origin
 * cookies) and all the shared types. No imports of `next/headers` or
 * other server-only modules, this file gets bundled into the browser.
 *
 * Server components import `apiServer` from `./api-server` (NOT this file).
 */

export class ApiError extends Error {
  constructor(public status: number, message: string, public body?: unknown) {
    super(message);
  }
}

/**
 * Human-readable fallback when the server sent no usable `detail`.
 *
 * Says what the status actually means AND keeps the code visible, so a support conversation can start
 * from "504 at the gateway" instead of "it said it failed".
 */
export function describeHttpFailure(status: number): string {
  if (status === 401) return 'Your session expired (401). Sign in again and retry.';
  if (status === 403) return 'This account is not allowed to do that (403).';
  if (status === 404) return 'Not found (404).';
  if (status === 413) return 'That request was too large (413).';
  if (status === 429) return 'Too many requests (429). Wait a moment and retry.';
  if (status === 502 || status === 503) {
    return `The service was unreachable (${status}). It may be restarting. Retry in a moment.`;
  }
  if (status === 504) {
    return 'The request timed out at the gateway (504). The work may still be running on the server.';
  }
  if (status >= 500) return `The server errored (${status}). This has been logged.`;
  return `Request failed (${status}).`;
}

/** Shared response parser. Underscore-prefixed because the server module
 *  re-uses it; not intended as a public API. */
export async function _parse<T>(res: Response): Promise<T> {
  const text = await res.text();
  const parsed = text ? _tryJson(text) : { ok: true as const, value: undefined };
  const body = parsed.ok ? parsed.value : text;
  if (!res.ok) {
    const serverDetail =
      (body && typeof body === 'object' && 'detail' in body && typeof (body as any).detail === 'string')
        ? (body as any).detail
        : '';
    // Never fall back to `res.statusText`: it is ALWAYS an empty string over HTTP/2, which production
    // serves. Any error that isn't JSON-with-a-detail, a gateway 502/504 HTML page, a dropped
    // upstream, a bare 500. Therefore produced an ApiError with an empty message, and callers that
    // render `e.message` showed a blank or generic error with no way to tell what happened. That is
    // how a real failure reached a user as "Failed to generate the assessment." with no diagnosis.
    throw new ApiError(res.status, serverDetail || describeHttpFailure(res.status), body);
  }
  // A 2xx response whose body arrived but doesn't parse as JSON means the
  // response was truncated or replaced by a gateway/proxy error page. Common
  // when a long scan exceeds an upstream timeout and the connection is cut
  // after the status line. Silently returning the raw string here used to
  // leave callers with `data` set to an unrenderable string, so the UI showed
  // nothing at all. Surface it as an error instead.
  if (text && !parsed.ok) {
    throw new ApiError(
      res.status,
      'The server returned an incomplete response. The request may have ' +
        'timed out. Try again, and reduce the batch size if it persists.',
      body,
    );
  }
  return body as T;
}

type JsonParse = { ok: true; value: unknown } | { ok: false };
function _tryJson(s: string): JsonParse {
  try { return { ok: true, value: JSON.parse(s) }; } catch { return { ok: false }; }
}

/** Browser-side fetch. Sends the Clerk session token so FastAPI can resolve the user; also keeps
 *  same-origin cookies as a fallback during the auth migration. */
export async function apiClient<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  let authHeader: Record<string, string> = {};
  try {
    const clerk = (globalThis as { Clerk?: { session?: { getToken?: () => Promise<string | null> } } }).Clerk;
    const token = await clerk?.session?.getToken?.();
    if (token) authHeader = { authorization: `Bearer ${token}` };
  } catch {
    /* Clerk not ready / signed out. Fall back to the cookie */
  }
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...authHeader,
      ...init.headers,
    },
    credentials: 'same-origin',
  });
  return _parse<T>(res);
}

// ---------------------------------------------------------------------------
// Select-then-scan, the compile (free list) + score (paid selection) flow.
// ---------------------------------------------------------------------------
export interface CommenterCandidate {
  external_id: string;
  handle: string | null;
  comment: string | null;
  comment_count: number;
  avatar_url?: string | null;
  scanned: boolean;
}

export interface CommenterListResponse {
  platform: string;
  content_id: string;
  url: string | null;
  commenters: CommenterCandidate[];
  total: number;
  has_more: boolean;     // more commenters can still be pulled ("add 25/50 more")
  fetched_now: number;   // how many NEW commenters this call added
}

export interface ScoreJob {
  job_id: string;
  status: string;
  platform: string;
  url: string;
  investigation_slug: string;
}

/** FREE: list (and cache) a post's commenters. `fetch` > 0 pulls the next page; `refresh` rebuilds. */
export function listCommenters(
  url: string,
  opts: { fetch?: number; refresh?: boolean } = {},
): Promise<CommenterListResponse> {
  const body: Record<string, unknown> = { url };
  if (opts.fetch != null) body.fetch = opts.fetch;
  if (opts.refresh) body.refresh = true;
  return apiClient<CommenterListResponse>('/v1/scan/link/commenters', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** PAID: score only the selected commenters. Returns a job; poll /scan/link/status/{job_id}. */
export function scoreSelection(url: string, selected: string[]): Promise<ScoreJob> {
  return apiClient<ScoreJob>('/v1/scan/link/score', {
    method: 'POST',
    body: JSON.stringify({ url, selected }),
  });
}

// ---------------------------------------------------------------------------
// Funnel: claim a shared report you arrived from.
// ---------------------------------------------------------------------------

/** The caller's own copy of a shared investigation, after claiming it. */
export interface ClaimedInvestigation {
  slug: string;
  label: string;
  /** The post the report is about, so the app can send them to /investigate?url=... */
  input_url: string;
  platform: string | null;
  /** True when this token was already claimed by this account (a refresh, a retried request). */
  already_claimed: boolean;
}

/**
 * Copy a publicly shared investigation into the signed-in user's own archive.
 *
 * Safe to call more than once: the server keys the claim on (user, token) and returns the copy that
 * already exists rather than duplicating a payload that is routinely megabytes.
 */
export function claimSharedInvestigation(shareToken: string): Promise<ClaimedInvestigation> {
  return apiClient<ClaimedInvestigation>('/v1/investigations/claim', {
    method: 'POST',
    body: JSON.stringify({ share_token: shareToken }),
  });
}

// ---------------------------------------------------------------------------
// The free pre-login scan, the SAME compile → select → analyze flow as above,
// anonymous, X-only, capped at 25 repliers, ONE scan per visitor.
// ---------------------------------------------------------------------------

/** FREE (no account): list an X post's repliers so a visitor can pick who to analyze. */
export function demoListCommenters(url: string): Promise<CommenterListResponse> {
  return apiClient<CommenterListResponse>('/v1/scan/demo/commenters', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

/** FREE (no account): analyze the selected repliers. Runs synchronously and returns the result. */
export function demoScoreSelection(
  url: string,
  selected: string[],
): Promise<ComprehensiveScanResult> {
  return apiClient<ComprehensiveScanResult>('/v1/scan/demo/score', {
    method: 'POST',
    body: JSON.stringify({ url, selected }),
  });
}

// ---------------------------------------------------------------------------
// Feedback, any signed-in user submits; admins read a searchable queue.
// ---------------------------------------------------------------------------
export interface FeedbackEntry {
  id: number;
  user_id: number | null;
  email: string | null;
  category: string;
  message: string;
  page: string | null;
  created_at: string;
}
export interface FeedbackListResponse { feedback: FeedbackEntry[]; total: number; }

export function submitFeedback(input: { message: string; category?: string; page?: string }): Promise<{ ok: boolean; id: number }> {
  return apiClient('/v1/feedback', { method: 'POST', body: JSON.stringify(input) });
}
export function listFeedback(params: { q?: string; user?: string; limit?: number; offset?: number } = {}): Promise<FeedbackListResponse> {
  const qs = new URLSearchParams();
  if (params.q) qs.set('q', params.q);
  if (params.user) qs.set('user', params.user);
  qs.set('limit', String(params.limit ?? 100));
  if (params.offset) qs.set('offset', String(params.offset));
  return apiClient<FeedbackListResponse>(`/v1/feedback?${qs.toString()}`);
}

// ---------------------------------------------------------------------------
// Report disputes: the recourse an accused account has.
//
// Anyone can file one from a public report without an account (that is the point: the person a
// report is about is never a customer). Reading and resolving the queue is admin only, because it
// holds complainants' contact details.
//
// The important asymmetry, mirrored from app/routes/reports.py: filing does NOT unpublish anything,
// or anyone could silence any report by claiming to be named in it. Unpublishing is a decision an
// admin makes here, and it works on ANY report, not only one the admin owns.
// ---------------------------------------------------------------------------
export const DISPUTE_STATUSES = ['open', 'reviewing', 'upheld', 'rejected'] as const;
export type DisputeStatus = (typeof DISPUTE_STATUSES)[number];

export interface ReportDispute {
  id: number;
  share_token: string;
  /** The account the complainant says the report is wrong about. Optional: they need not tell us. */
  subject_handle: string | null;
  contact: string | null;
  reason: string;
  status: DisputeStatus;
  resolution_note: string | null;
  created_at: string | null;
  resolved_at: string | null;
  /** Whether /r/<token> still resolves. False once the token has been revoked. */
  report_still_public: boolean;
}

export function listDisputes(status: DisputeStatus | 'all' = 'open'): Promise<ReportDispute[]> {
  return apiClient<ReportDispute[]>(`/v1/admin/disputes?status=${encodeURIComponent(status)}`);
}

export function resolveDispute(
  id: number,
  body: { status: DisputeStatus; note?: string; unpublish?: boolean },
): Promise<ReportDispute> {
  return apiClient<ReportDispute>(`/v1/admin/disputes/${id}`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// The network detector's finding queue. Admin only, on every route.
//
// A finding here names REAL PEOPLE as running together, on evidence that is statistical rather than
// certain, so it is an operator's lead and never a customer-facing verdict.
//
// The judgements are the reason this queue has an interface at all. Every threshold in
// `app/netdetect` is reasoned rather than fitted, because no labelled corpus of coordinated accounts
// exists, and the calibration report refuses to recommend anything until 30 findings have been
// judged with at least 8 of each class. Nobody produces thirty judgements through curl.
// ---------------------------------------------------------------------------

export const NETDETECT_STATUSES = ['open', 'dismissed', 'confirmed'] as const;
export type NetdetectStatus = (typeof NETDETECT_STATUSES)[number];

export interface NetdetectEvidence {
  family: string;
  kind: string;
  shared_by: number;
  /** How many accounts in the whole corpus exhibit it: the denominator of the rarity claim. */
  corpus_count: number;
  surprise: number;
  sentence: string;
}

export interface NetdetectCorroboration {
  /** CONTEXT ONLY. Does not separate an operation from a newsroom. Never rank on it. */
  log_lr: number;
  pairs_with_history: number;
  /** The half that discriminates: prior evidence of the operator's own acts. */
  hard_pairs: number;
  /** Distinct EARLIER posts. The post being scanned is excluded, so a set cannot corroborate itself. */
  contexts: string[];
  families: string[];
  hard_families: string[];
  /** False means nobody looked, which is not a statement about the people named. */
  checked: boolean;
  sentence: string;
}

export interface NetdetectFinding {
  id: number;
  investigation_id: number | null;
  context_id: string | null;
  platform: string;
  members: string[];
  member_count: number;
  score: number;
  /** Null means "not compared against the shuffled search", which must never be read as passing it. */
  corrected_p: number | null;
  by_family: Record<string, number>;
  needs_adjudication: string | null;
  /**
   * Members that do not carry the finding. A pointer for review, NEVER an exclusion (they are still
   * in `members`) and never a confidence score.
   */
  weakly_attached: string[];
  /** Why no membership verdict was reached, or null when one was. */
  attachment_note: string | null;
  /**
   * Whether the membership test ran. THE LOAD-BEARING FLAG: an empty `weakly_attached` means "every
   * member carries this finding" when this is true and "we could not tell" when it is false, and
   * those are opposite statements about the people named.
   */
  attachment_checked: boolean;
  /**
   * What the accumulating graph already held about these members, from OTHER posts, as of the last
   * run. Null means the lookup did not run, NEVER that they had not been seen together.
   *
   * Read `hard_pairs`, not `log_lr`. Measured, a planted operation and the professional-beat
   * control both saturate the total and the newsroom carried MORE linked pairs, so the total does
   * not separate them. Only prior evidence in the hard families (identity, network) does.
   */
  corroboration: NetdetectCorroboration | null;
  evidence: NetdetectEvidence[];
  corpus_size: number;
  null_shuffles: number;
  null_threshold: number | null;
  status: NetdetectStatus;
  dismissal_reason: string | null;
  confirmed: boolean;
}

export interface Formation {
  formation_key: string;
  platform: string;
  label: string | null;
  /**
   * forming / active / dormant / resurgent. RESURGENT exists only because the entity survived the
   * quiet period, and it is the phase a per-run detector can never report.
   */
  phase: string;
  previous_phase: string | null;
  member_count: number;
  sighting_count: number;
  /** Distinct posts. A re-scan of one post is one sighting, never two. */
  context_count: number;
  families: string[];
  profile_size: number;
  first_seen: string | null;
  last_seen: string | null;
  status: string;
  /**
   * What the per-account engine makes of the members, computed AFTER detection and never fed back
   * into it. `posture: "concealed"` is the finding only this system can produce.
   */
  composition: { posture?: string; median?: number; note?: string; scored?: number };
}

export function listFormations(): Promise<Formation[]> {
  return apiClient<Formation[]>('/v1/admin/netdetect/formations');
}

export interface FormationPlacement {
  external_id: string;
  handle: string;
  /** Characterisation only: placement reads behaviour, never this. Null means never scored. */
  omi_score: number | null;
  /**
   * Placed in a known operation while reading as an ordinary account on its own. THE ROW TO READ
   * FIRST: an account the per-account engine already flags is one an analyst could have found
   * without this; one that would pass an individual review is not.
   */
  concealed: boolean;
  assignment: {
    formation_key: string;
    label: string | null;
    phase: string | null;
    posterior: number;
    hard_evidence: number;
    by_family: Record<string, number>;
    assigned: boolean;
    matched: { family: string; kind: string; value: string; sentence: string }[];
  };
}

export interface FormationSweep {
  slug: string;
  accounts_weighed: number;
  formations_considered: number;
  placed: FormationPlacement[];
  /**
   * A COUNT, never a list of names. An account placed in nothing is one this deployment has never
   * catalogued doing this before, which is not innocence. See `not_a_clearance`.
   */
  unplaced: number;
  truncated: boolean;
  /** A THIRD state: nobody looked, which is not the same as "weighed and matched nothing". */
  nothing_catalogued: boolean;
  /** How many placed accounts would have passed an individual review. */
  concealed: number;
  not_a_clearance: string;
}

export function sweepFormations(slug: string): Promise<FormationSweep> {
  return apiClient<FormationSweep>(
    `/v1/admin/netdetect/formations/sweep?slug=${encodeURIComponent(slug)}`,
    { method: 'POST' },
  );
}

export function listNetdetectFindings(
  status: NetdetectStatus | 'all' = 'open',
): Promise<NetdetectFinding[]> {
  return apiClient<NetdetectFinding[]>(
    `/v1/admin/netdetect/findings/all?status=${encodeURIComponent(status)}`,
  );
}

export function judgeNetdetectFinding(
  id: number,
  verdict: 'dismiss' | 'confirm',
  reason: string,
): Promise<NetdetectFinding> {
  return apiClient<NetdetectFinding>(`/v1/admin/netdetect/findings/${id}/${verdict}`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  });
}

export interface NetdetectSweepRow {
  value: number;
  confirmed_kept: number;
  dismissed_kept: number;
  dismissed_removed: number;
}

export interface NetdetectSweep {
  constant: string;
  /** The file to edit BY HAND if the recommendation is accepted. Nothing here changes a threshold. */
  where: string;
  current: number;
  stricter_direction: string;
  rows: NetdetectSweepRow[];
  proposed: number | null;
  recommendation: string | null;
}

export interface NetdetectCalibration {
  confirmed: number;
  dismissed: number;
  open: number;
  /** False while the reservoir is too thin to fit anything. The sweeps still come back. */
  sufficient: boolean;
  insufficient_reason: string;
  sweeps: NetdetectSweep[];
  families: {
    family: string; weight: number; hard: boolean;
    mean_in_confirmed: number; mean_in_dismissed: number;
    present_in_confirmed: number; present_in_dismissed: number; separation: number;
  }[];
  recommendations: string[];
  caveats: string[];
}

export function netdetectCalibration(): Promise<NetdetectCalibration> {
  return apiClient<NetdetectCalibration>('/v1/admin/netdetect/findings/calibration');
}

// ---------------------------------------------------------------------------
// Coordinated-campaign detection. Admin only, on every route.
//
// The detector is deterministic: no model call, no network, no provider quota. It clusters the
// accounts an investigation scored at 70 or above, using evidence those accounts themselves
// produced. Its thresholds are reasoned rather than fitted against a labelled corpus, so a finding
// is a lead for an operator to review and nothing here is reachable from the customer app, the
// public report, or the exports.
// ---------------------------------------------------------------------------
export const COORDINATION_FILTERS = ['open', 'dismissed', 'all'] as const;
export type CoordinationFilter = (typeof COORDINATION_FILTERS)[number];

/** Families of independent evidence. Fusion takes the strongest edge WITHIN a family and combines
 *  ACROSS families, so two methods reading the same material cannot corroborate each other. */
export const COORDINATION_FAMILY_LABEL: Record<string, string> = {
  text: 'Repeated text',
  timing: 'Synchronised arrival',
  network: 'Shared targets',
  infrastructure: 'Shared tooling',
  identity: 'Account provisioning',
};

export interface CoordinationMember {
  external_id: string;
  handle: string;
  /** The score the cohort was cut on, 0-100. Null when the account is no longer in the payload. */
  score: number | null;
}

export interface CoordinationArtifact {
  method: string;
  family: string;
  /** The two handles this specific claim is about. */
  pair: string[];
  sentence: string;
  /** The raw material the accounts produced. Empty artifacts are dropped before this point. */
  artifact: string;
  statistic: [string, number] | null;
}

export interface CoordinationFinding {
  finding_id: string;
  /** 'corroborated' is a campaign. 'lead' did not clear the bar and is never written as one. */
  label: 'corroborated' | 'lead';
  /** Calibrated P(coordinated) for the group: the WEAKEST member's admitting probability, not the
   *  strongest and not the mean. A group is only as defensible as the least defensible person in
   *  it, and that person is the one harmed if it is wrong. */
  score: number;
  capped: boolean;
  /** Share of all possible member pairs that carry evidence. */
  density: number;
  /** handle -> that account's own probability of being coordinated with this group. Every member
   *  had to clear the bar on its own evidence, so no one is carried in by their neighbours. */
  member_posteriors: Record<string, number>;
  /** The prior, then each family's contribution, then the total. A probability with no visible
   *  derivation is exactly as unaccountable as the score it replaced. */
  derivation: string;
  prior: number;
  lr_version: string;
  members: CoordinationMember[];
  families_fired: string[];
  families_silent: string[];
  methods: string[];
  evidence: string[];
  notes: string[];
  artifacts: CoordinationArtifact[];
}

export interface CoordinationDetection {
  investigation_slug: string;
  investigation_label: string;
  platform: string;
  computed_at: string | null;
  passes: number;
  /** 'analyst' means the cohort was cut on the customer-visible OMI score, 'engine' on the
   *  deterministic probability (which is what runs when the analyst is unreachable). */
  score_source: 'analyst' | 'engine';
  scanned_total: number;
  cohort_size: number;
  finding_count: number;
  campaign_count: number;
  best_score: number;
  best_label: string;
  status: string;
  thresholds_version: string;
}

export interface CoordinationDetectionDetail extends CoordinationDetection {
  findings: CoordinationFinding[];
  lone_high_scorers: string[];
  notes: string[];
  resolution_note: string | null;
}

export interface CoordinationDetectionsResponse {
  detections: CoordinationDetection[];
  total: number;
  open_count: number;
  campaign_count: number;
}

export function listCoordinationDetections(
  opts: { status?: CoordinationFilter; onlyCampaigns?: boolean } = {},
): Promise<CoordinationDetectionsResponse> {
  const q = new URLSearchParams({ status: opts.status ?? 'open' });
  if (opts.onlyCampaigns) q.set('only_campaigns', 'true');
  return apiClient<CoordinationDetectionsResponse>(`/v1/admin/coordination?${q.toString()}`);
}

export function getCoordinationDetection(slug: string): Promise<CoordinationDetectionDetail> {
  return apiClient<CoordinationDetectionDetail>(
    `/v1/admin/coordination/${encodeURIComponent(slug)}`,
  );
}

export function rerunCoordinationDetection(slug: string): Promise<CoordinationDetectionDetail> {
  return apiClient<CoordinationDetectionDetail>(
    `/v1/admin/coordination/${encodeURIComponent(slug)}/rerun`,
    { method: 'POST' },
  );
}

export function dismissCoordinationDetection(
  slug: string,
  note: string,
): Promise<CoordinationDetectionDetail> {
  return apiClient<CoordinationDetectionDetail>(
    `/v1/admin/coordination/${encodeURIComponent(slug)}/dismiss`,
    { method: 'POST', body: JSON.stringify({ note }) },
  );
}

export function reopenCoordinationDetection(slug: string): Promise<CoordinationDetectionDetail> {
  return apiClient<CoordinationDetectionDetail>(
    `/v1/admin/coordination/${encodeURIComponent(slug)}/reopen`,
    { method: 'POST' },
  );
}

// ---------------------------------------------------------------------------
// Upstream API spend. Admin only.
//
// `api_calls` is the number that BILLS (twitterapi.io charges per call), not the number of requests
// this product served: one compile can page the provider several times. Reading the two apart is the
// point, which is why `requests` is carried separately.
// ---------------------------------------------------------------------------
export interface UpstreamUsageSnapshot {
  date: string;
  today_api_calls: number;
  per_user_budget: number;
  global_budget: number;
  /** Null when the deployment-wide ceiling is disabled (budget 0). */
  global_remaining: number | null;
  by_day: { date: string; api_calls: number; requests: number }[];
  by_platform: { platform: string; api_calls: number }[];
  heaviest_users_today: { user_id: string; api_calls: number; requests: number }[];
}

// ---------------------------------------------------------------------------
// Shared response types (mirror app/schemas.py. Kept thin until Phase 1.5
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
  /** Pre-launch lockdown: when true, only admins may use the product. Decided by the API. */
  lockdown?: boolean;
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

/** Detector taxonomy. Mirrors aggregate.DISCRIMINATIVE_DETECTORS exactly.
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

// Founder learning (master-plan Phase 4). Mirrors apps/api/app/routes/learning.py.
export interface WtpPromptStatus {
  show_wtp: boolean;
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
// Scan / investigation payload (mirrors apps/api/app/schemas.py. Kept light).
// ---------------------------------------------------------------------------

export interface SignalResult {
  name: string;
  probability: number;
  confidence: number;
  evidence: string[];
  sub_signals: Record<string, number>;
  /**
   * Supplemental signals (e.g. ai_writing) are computed and shown for context
   * but excluded from the suspicion score. AI-assisted writing is not evidence
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
  /** Raw profile metadata, the objective facts the analyst reasons from (and the account view can
   *  show). `null` means the platform genuinely didn't return the field, not zero/false. */
  follower_count?: number | null;
  following_count?: number | null;
  account_created_at?: string | null;
  bio?: string | null;
  verified?: boolean | null;
  /** True depth of this account's pulled history, independent of how many samples ride along. */
  history_size?: number;
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
  /** Signed per-detector attribution: what RAISED vs LOWERED the score, 
   *  including the exculpatory "community" footprint. Optional: empty on cached
   *  commenters and absent from investigations saved before this shipped. */
  contributions?: DetectorContribution[];
}

export interface DetectorContribution {
  name: string;
  headline: string;
  probability: number;
  confidence: number;
  impact: number; // share of total score movement, 0-1
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
  // P3.1.6, the AI-native Comment Analysis compatibility output. Present only when Comment
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
  /** The Omi Analyst's reading, inlined on the response. Signed-in scans leave this null and poll
   *  /v1/investigations/{slug}/analyst instead; the anonymous free scan has no saved investigation
   *  to poll, so it carries the assessment here. Null when the analyst is off or the call failed, 
   *  the deterministic result above is unaffected. */
  analyst_assessment?: AnalystAssessment | null;
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
  /** youtube | x | unknown. Derived at list time for archive cards. */
  platform: string;
  /** Public CDN thumb (YouTube hqdefault) when available; null for X/unknown. */
  thumbnail_url: string | null;
}

export interface InvestigationsListResponse {
  investigations: InvestigationSummary[];
}

export interface InvestigationDetailResponse {
  slug: string;
  label: string;
  input_url: string;
  kind: string;
  /** "x" | "youtube" | "unknown". Resolved server-side from the denormalised column, never from the
   *  payload. Decides which graphs an account on this investigation may be added to: a graph's
   *  members inherit ITS platform and the coordination-edge query filters on that, so a mismatched
   *  member is stored mislabelled and can never draw an edge. See `lib/graph-membership`. */
  platform: string;
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

// Omi Analyst. Structured, evidence-bounded assessment of an investigation.
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

// The eight dimensions the analyst scores each account on, in the order it must return them
// (apps/api app.reasoning.prompts.comprehensive_investigation_template.COMPREHENSIVE_SIGNAL_NAMES).
// The backend normalises whatever the model sends into exactly these eight, in this order, so the UI
// can render eight rows unconditionally.
export const ACCOUNT_SIGNAL_KEYS = [
  'temporal',
  'semantic',
  'ai_writing',
  'profile',
  'voice',
  'engagement',
  'account_maturity',
  'history_authenticity',
] as const;
export type AccountSignalKey = (typeof ACCOUNT_SIGNAL_KEYS)[number];

// Reader-facing name + one line of "what is this dimension" for each. Kept in sync with the
// _SIGNAL_GUIDE the model reads, so the explanation a customer sees matches what was scored.
export const ACCOUNT_SIGNAL_META: Record<AccountSignalKey, { label: string; description: string }> = {
  temporal: {
    label: 'Posting rhythm',
    description: 'Machine-regular intervals, sudden bursts, or a dormant account that woke up to post here.',
  },
  semantic: {
    label: 'Content repetition',
    description: 'Templated or near-identical text reused across the same account\'s own history.',
  },
  ai_writing: {
    label: 'Machine-written prose',
    description: 'Generic, fluent, personality-free phrasing. Writing well is not a tell on its own.',
  },
  profile: {
    label: 'Profile coherence',
    description: 'Account age against the follower and following balance, bio, verification, display name.',
  },
  voice: {
    label: 'Personal voice',
    description: 'Lived specifics and real opinions, versus interchangeable filler.',
  },
  engagement: {
    label: 'Engagement farming',
    description: 'One-line praise, emoji-only replies, follow-for-follow, link-in-bio and giveaway pitches.',
  },
  account_maturity: {
    label: 'Account maturity',
    description: 'Age measured against what the account has actually built: audience, history, continuity.',
  },
  history_authenticity: {
    label: 'History authenticity',
    description: 'Whether the posting history reads like one real life or like filler assembled to look populated.',
  },
};

// One scored dimension behind an account's OMI score. `score` is 0-100 in the SAME direction as the
// OMI score (0 = reads like a genuine person, 100 = a strong bought tell).
//
// `score: null` is meaningful and is NOT zero: it means the evidence this dimension needs was never
// collected (an account with no posting history cannot be scored on rhythm). Rendering it as 0 would
// turn "we could not tell" into "this looks genuine", which is exactly the overclaim the protocol
// forbids. `reason` is the model's one plain-English sentence naming the fact that produced the score.
export interface AccountSignal {
  name: AccountSignalKey;
  score: number | null;
  reason: string | null;
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
  // The eight dimensions behind this account's OMI score, always all eight and always in
  // ACCOUNT_SIGNAL_KEYS order (the backend normalises the model's array before persisting). Absent
  // only on assessments generated before per-signal scoring shipped.
  signals?: AccountSignal[];
  // How much evidence this account's read rests on, 0-100. Distinct from the score: a confident 12
  // and an uncertain 12 are different findings. Always knowable, so never null.
  confidence?: number;
  assessment: string;
  citations: string[];
  resolved: boolean;
  handle?: string;
  external_id?: string;
  // Raw account metadata (from the scan). Shown alongside the AI's per-account score.
  follower_count?: number;
  following_count?: number;
  account_created_at?: string;
  post_count?: number;
  engine_probability?: number;
  /** @deprecated legacy engine field. Replaced by omi_score + engine_probability */
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
  // `summary_not_certified` is the salvage case: every account carries the model's own read and the
  // investigation-level summary above them did not certify. Mirrors `completion.py`.
  incomplete_kind:
    | 'truncated_output' | 'missing_assessments' | 'omitted_input' | 'summary_not_certified' | null;
  reason: string;
  estimated_remaining_commenters: number;
}

export interface AnalystAssessment {
  verdict: string;
  /** THE OMI SCORE: the analyst's single composite authenticity-risk score, 0-100 (higher = stronger
   *  evidence of inauthentic/coordinated behavior). The only investigation score. */
  omi_score: number;
  suspicion_tier: string;
  /** DEPRECATED: the legacy 0-1 inauthenticity probability. Superseded by omi_score; may be absent. */
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
  /** Batched generation progress (selections > the per-request account cap run as parallel ≤cap
   *  batches, merged first-to-last). Present only on batched runs; `complete` false means more
   *  batches are still landing and the client should keep polling. */
  /*  `done` counts batches ATTEMPTED (so the readout moves when one fails rather than freezing),
   *  which makes it equal to `total` on any finished run. `landed` counts the batches that actually
   *  produced accounts, and is therefore the COVERAGE figure. Optional: entries written before it
   *  existed have no value, and the UI falls back rather than claiming coverage it cannot know. */
  batching?: {
    total: number;
    /** Batches ATTEMPTED. Advances when one fails, so a run containing a failure still visibly moves. */
    done: number;
    /** Batches that PRODUCED accounts. Coverage, which is a different question from `done`. */
    landed?: number;
    batch_size: number;
    /** The RUN IS OVER. Not "every batch succeeded". */
    complete: boolean;
    /** The per-batch record. Exact, so no reader has to infer a batch's state from the counts
     *  above: those three numbers look interchangeable and every reader that guessed wrong shipped
     *  a bug. Absent on entries written before it existed. See app/reasoning/batch_plan.py. */
    batches?: Array<{
      index: number;
      state: 'pending' | 'running' | 'done' | 'failed';
      accounts: number;
      /** Which model call this batch is on (1 = first). A batch on its second attempt is otherwise
       *  indistinguishable from a slow first one, and a retry is the slowest thing that happens to
       *  one batch. Absent on entries written before it was recorded. */
      attempt?: number;
    }>;
  };
  // The engine's corroboration state, echoed onto the assessment (overlaid from the deterministic
  // Floor, never model-fabricated. Apps/api runtime.py). It bounds the coordination read: a maximal
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
  // commenter. Surfaced with a flag, never dropped. Empty/absent when the model produced none.
  commenter_assessments?: CommenterAssessment[];
  // Full-investigation completion status (Phase 5H): whether every commenter received AI reasoning.
  completion?: CompletionStatus;
  // The six domain-reasoning sections of the single comprehensive Mistral response (present when the
  // comprehensive path produced them). Rendered as views over ONE inference, never fetched per panel.
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
  // never present Floor prose as AI reasoning, it keys off this. The remaining fields power the
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
    provider?: string;                    // the analyst backend that served this run
    requested_model?: string | null;      // e.g. "@preset/omi-master-v1"
    served_model?: string | null;         // the model the gateway actually ran, e.g. "openai/gpt-5-mini"
    served_model_expected?: string | null;   // the model this deployment expects to be served
    served_model_verified?: boolean | null;  // true = served model IS the expected one; false = swapped; null = n/a
    openrouter_preset?: string | null;    // the compiled protocol preset id
    master_prompt_version?: string | null;
    master_prompt_hash?: string | null;   // "map:…". What Omi expects the preset to contain
    canonical_schema_id?: string | null;
    // pipeline-stage flags
    request_completed?: boolean;
    json_received?: boolean;
    validation_passed?: boolean;
    // The synthesis wrapper floored but real per-account reads survived (a mixed batched run, or a
    // response whose wrapper failed validation while its rows were fine). Distinct from
    // `model_backed` on purpose: that one still answers no, and it is what gates the operator alert
    // and the self-heal regeneration. Absent on entries written before salvage existed.
    account_reads_salvaged?: boolean;
    // Per-batch outcome for a batched run. `accounts` is how many reads that batch actually
    // produced, so 0 means it was attempted and came back empty. This is what lets the progress
    // track show a failed batch as failed instead of counting it as done: `batching.done` counts
    // ATTEMPTS (so the readout moves when one fails) and cannot tell the two apart on its own.
    batches?: {
      total: number;
      done: number;
      size: number;
      traces?: Array<{
        batch: number;
        accounts: number;
        model_backed?: boolean;
        served_model?: string | null;
      }>;
    };
    fallback_reason?: string | null;
    governor_verdict?: string | null;
    comprehensive_structurally_valid?: boolean;
    canonical_validation_errors?: string[] | null;  // why a 200 model response failed schema → Floor
    // call metrics (authoritative gateway usage)
    endpoint_request_id?: string | null;  // upstream generation id
    endpoint_latency_ms?: number | null;
    endpoint_cost_usd?: number | null;
    input_tokens?: number | null;
    output_tokens?: number | null;
    total_tokens?: number | null;
    response_status?: number | null;
    endpoint_error?: string | null;
    // Phase 5H. Full-investigation completion (also on `completion`, mirrored here for the trace panel)
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
  /** 'partial' = a batched run's assessment-so-far (first batches scored); keep polling. */
  status: 'ready' | 'generating' | 'partial';
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
  /**
   * Funnel facts on a shared report. Each is real or absent, never estimated.
   *
   * `commenters_available` is how many commenters were COMPILED for the post against
   * `commenters_scanned`, so the gap is a checkable statement of what the report leaves out. It is
   * null on investigations saved before it was recorded. `read_count` is the deduped public-view
   * count for this token.
   *
   * Nothing here may be filled in with a guess. This is a page about fabricated engagement; an
   * invented number on it would discredit every real number beside it.
   */
  commenters_scanned?: number;
  commenters_available?: number | null;
  read_count?: number | null;
}

export interface ReportVerdict {
  overall_probability: number;
  overall_tier: Tier;
  summary: string;
  convergence_score: number;
}

/**
 * One row of the full scanned-account table on a public report.
 *
 * Deliberately lighter than `ReportCommenter`: no summary, reasons, or recent_activity. Those are
 * per-account evidence blobs, and carrying them for a whole comment section would multiply the
 * response by data the table never renders.
 */
export interface ReportCommenterRow {
  handle: string;
  external_id: string;
  tier: Tier;
  overall_probability: number;
  intent_label: string | null;
  /** The analyst's own read, merged on when it reached this account. Absent means not assessed, which
   *  is different from assessed and silent. The eight-signal breakdown is NOT here: it is admin-only
   *  and this response is public. */
  omi_score?: number;
  analyst_tier?: Tier;
  assessment?: string;
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
  /** EVERY account the report scored, worst first, not just the flagged ones. */
  all_commenters?: ReportCommenterRow[];
  total_scanned?: number;
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

// User-curated named graphs. /v1/graphs/*
export interface UserGraphMemberOut {
  id: number;
  external_id: string;
  platform: string;
  handle: string;
  display_name: string | null;
  tier: Tier | null;
  /** The account's REAL score. null means it was not captured when this member was added, which is
   *  different from zero: the node renders unsized rather than confidently small. The client used
   *  to rebuild this from the tier band (high -> 0.9) and size every node by it, which is an
   *  invented figure on a surface whose whole claim is that it does not invent figures. */
  omi_score: number | null;
  avatar_url: string | null;
  added_at: string;
  /** Cluster from community detection over the graph's OWN edges. 0 = unconnected, which is the
   *  honest and most common state and is drawn as its own band rather than as a cluster of one. */
  community_id: number;
  /** How many other members this one links to. Zero is a real answer. */
  degree: number;
}

/** One link, with the reason it exists. Replaces `{a, b, strength}`, where strength was a per-scan
 *  mean cluster score: a number that is not a probability of anything, drawn as a line between two
 *  named people with nothing a reader could check. */
export interface GraphCoordinationEdge {
  a: string;
  b: string;
  /** P(coordinated | evidence): the calibrated posterior the detector itself decides on. */
  posterior: number;
  /** Independent evidence families that fired. TWO is the bar; one is never enough alone. */
  families: string[];
  /** Distinct posts the pair co-occurred under. Several unrelated ones is what makes it credible. */
  contexts: number;
  methods: string[];
  first_seen: string | null;
  last_seen: string | null;
}

/** An account NOT in the graph that links strongly into it. The old endpoint could not produce
 *  these at all, so a graph could only ever show its owner what they already knew to add. */
export interface GraphSuggestion {
  external_id: string;
  platform: string;
  posterior: number;
  linked_to: string;
  families: string[];
  contexts: number;
  /** How many DIFFERENT members it links to. Two or more outranks one strong link. */
  links_into_graph: number;
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
  edges: GraphCoordinationEdge[];
  suggestions: GraphSuggestion[];
  /** Distinct clusters among members. 0 when nothing is connected, which is not "one community". */
  community_count: number;
  /** True when the member list was capped. Said out loud rather than silently showing a subset. */
  truncated: boolean;
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
// Phase 10. Content Intelligence types
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
// Phase 12. Ground-truth labels
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

// Learned (ML) scorer status. /v1/intelligence/ml-status (admin)
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
// Phase C. Reply tree + engagement pods
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
// Mirrors app/intelligence/schemas.py. The flat 0-100 fields are the stable
// public contract; `dimensions` is the explainability layer.
// ---------------------------------------------------------------------------

export type RiskLevel = 'low' | 'medium' | 'high';

export interface DimensionContribution {
  detector: string;
  label: string;
  /** Detector probability AFTER any inversion the dimension applies (0-1). */
  contribution_probability: number;
  confidence: number;
  /** Share of the dimension this detector accounted for, 0-1. */
  weight_share: number;
  evidence: string[];
}

export interface IntelligenceDimension {
  key: string;
  label: string;
  description: string;
  /** 0-100 in the dimension's own direction. */
  score: number;
  confidence: number;
  is_risk: boolean;
  /**
   * Contextual dimensions (e.g. AI-generated content) are reported for
   * information but excluded from the composite risk score. AI-assisted
   * writing is not by itself a sign of inauthenticity. Render distinctly.
   */
  is_contextual?: boolean;
  contributions: DimensionContribution[];
}

export interface OmiScore {
  schema_version: number;
  // Flat public contract (all 0-100)
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
 * inauthenticity) and amplification (a behavioral proxy with no reach data, 
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
  // engagement / timing), not measured reach. Like/view/follower-velocity data
  // is not yet ingested. Surface that plainly rather than overclaiming
  // "artificial amplification" the engine cannot actually evidence.
  amplification_probability: {
    label: 'Amplification (behavioral proxy)',
    short: 'Amplification',
    caveat: 'Behavioral proxy. Inferred from coordination, engagement and timing, not measured reach (likes / views / follower velocity are not yet ingested). Read as a behavioral signal, not confirmed reach inflation.',
  },
  spam_probability:          { label: 'Spam behavior',          short: 'Spam' },
  ai_generation_probability: { label: 'AI-generated content',   short: 'AI generation' },
};
