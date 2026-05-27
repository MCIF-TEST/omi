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
  const body = text ? _safeJson(text) : undefined;
  if (!res.ok) {
    const detail =
      (body && typeof body === 'object' && 'detail' in body && typeof (body as any).detail === 'string')
        ? (body as any).detail
        : res.statusText;
    throw new ApiError(res.status, detail, body);
  }
  return body as T;
}

function _safeJson(s: string): unknown {
  try { return JSON.parse(s); } catch { return s; }
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
  auth_required: boolean;
  billing_configured: boolean;
  monthly_credit_grant: number;
  storage_ephemeral: boolean;
}

export interface HistoricalScan {
  scanned_at: string;
  overall_probability: number;
  confidence: number;
  tier: Tier;
  summary: string;
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
  recent_activity: Array<{
    text: string;
    created_at: string | null;
    parent_id: string | null;
    like_count: number | null;
  }>;
  activity_total: number;
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

export interface InvestigationSummary {
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
  target_id: string | null;
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
}

export interface CommentaryResponse {
  slug: string;
  text: string;
  provider: string;
  tokens_used: number;
  generated_at: string;
  cached: boolean;
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
  trend: TrendInfo;
}
