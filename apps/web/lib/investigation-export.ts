/**
 * The investigation results as a table: one row per account, for a spreadsheet or the clipboard.
 *
 * Pure functions, no DOM and no React, so the row-building and the delimiting are testable without
 * rendering anything. `components/shared/export-results.tsx` is the button pair that calls them.
 *
 * Three decisions worth keeping:
 *
 * 1. **Every account the scan scored, not only the ones the analyst reached.** The engine's own list
 *    (`payload.video.commenters`) is the spine and the analyst's per-account reads are left-joined
 *    onto it. A batched run can finish with accounts the model never returned, and an export that
 *    quietly dropped them would understate the scan: the customer paid a credit for those accounts.
 *    They come out with their engine tier and an empty `omi_score`, which reads as "scanned, not
 *    assessed" rather than as a clean result.
 * 2. **The columns are driven by the data, never by a second copy of the gate.** `signals` and
 *    `confidence` are admin-only (`ADMIN_ONLY_ACCOUNT_FIELDS` in the API), and the assessment this
 *    file receives has already been through `assessment_for_viewer`. So the export asks "did any row
 *    arrive with signals?" rather than asking who the viewer is. A hardcoded column list here would
 *    be exactly the field-shredding trap the analyst coercion layer already paid for once, in the
 *    other direction: a list that has to be updated by hand drifts, silently.
 * 3. **The join is on `external_id`, never the handle.** Handles are mutable and two accounts can
 *    present the same display name.
 */
import { ACCOUNT_SIGNAL_KEYS, type AccountSignalKey, type CommenterAssessment, type Tier } from './api';

/** The subset of an engine commenter row the export needs. Projected on the server so the whole
 *  multi-megabyte scan payload never has to cross into the client bundle to produce a table. */
export interface ScannedAccount {
  handle: string | null;
  external_id: string;
  tier: Tier | null;
  /** 0..1. The coordination-adjusted probability when the engine produced one, else the raw score. */
  probability: number | null;
  intent_label: string | null;
}

export interface ExportRow {
  handle: string;
  account_id: string;
  /** The analyst's per-account OMI score, 0-100. Null when the model never reached this account. */
  omi_score: number | null;
  tier: string;
  engine_tier: string;
  /** The engine's own probability rendered 0-100, kept beside the analyst's score rather than
   *  blended into it. They answer different questions and a single merged number would hide which
   *  one moved. */
  engine_score: number | null;
  followers: number | null;
  following: number | null;
  account_created: string;
  account_age_days: number | null;
  posts: number | null;
  intent: string;
  /** Admin-only today; present only when the served assessment carried it. */
  confidence: number | null;
  /** Admin-only today; null when the served assessment carried no breakdown. */
  signals: Partial<Record<AccountSignalKey, number | null>> | null;
  assessment: string;
}

/** Minimal structural view of the stored scan payload. Deliberately not `ComprehensiveScanResult`:
 *  this reads two fields and should not fail to compile when an unrelated one changes. */
interface PayloadShape {
  video?: { commenters?: unknown } | null;
}

/**
 * Every account the scan scored, projected down to what a table needs.
 *
 * Runs on the server (the investigation page already holds the payload), so the client is handed a
 * few kilobytes instead of the whole `payload_json`, which for a 150-account investigation carries
 * every account's evidence, posts and analyst sections and would otherwise be serialised into the
 * HTML for a button nobody may click.
 */
export function scannedAccountsFrom(payload: unknown): ScannedAccount[] {
  const rows = (payload as PayloadShape | null)?.video?.commenters;
  if (!Array.isArray(rows)) return [];
  const out: ScannedAccount[] = [];
  for (const raw of rows) {
    if (!raw || typeof raw !== 'object') continue;
    const c = raw as Record<string, unknown>;
    const external = c.external_id;
    if (typeof external !== 'string' || !external) continue;
    const adjusted = c.coordination_adjusted_probability;
    const overall = c.overall_probability;
    out.push({
      handle: typeof c.handle === 'string' ? c.handle : null,
      external_id: external,
      tier: typeof c.tier === 'string' ? (c.tier as Tier) : null,
      probability:
        typeof adjusted === 'number' ? adjusted : typeof overall === 'number' ? overall : null,
      intent_label: typeof c.intent_label === 'string' ? c.intent_label : null,
    });
  }
  return out;
}

function ageDays(iso: string | undefined, now: number): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return Math.max(0, Math.floor((now - t) / 86_400_000));
}

function clampScore(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v)
    ? Math.max(0, Math.min(100, Math.round(v)))
    : null;
}

function signalMap(
  signals: CommenterAssessment['signals'],
): Partial<Record<AccountSignalKey, number | null>> | null {
  if (!Array.isArray(signals) || signals.length === 0) return null;
  const out: Partial<Record<AccountSignalKey, number | null>> = {};
  for (const key of ACCOUNT_SIGNAL_KEYS) out[key] = null;
  for (const s of signals) {
    if (!s || !ACCOUNT_SIGNAL_KEYS.includes(s.name)) continue;
    out[s.name] = typeof s.score === 'number' ? clampScore(s.score) : null;
  }
  return out;
}

/**
 * Join the scan's accounts with the analyst's reads, worst first.
 *
 * Sorted by the analyst's score where there is one and the engine's where there is not, because a
 * table someone opens to answer "who is worst" should already be in that order. It is a different
 * order from the on-screen list, which follows the batches so that results can appear as they land.
 *
 * `now` is injectable so the age column is deterministic under test.
 */
export function buildExportRows(
  scanned: ScannedAccount[],
  reads: CommenterAssessment[] | undefined,
  now: number = Date.now(),
): ExportRow[] {
  const byId = new Map<string, CommenterAssessment>();
  for (const r of reads ?? []) {
    if (r?.resolved && typeof r.external_id === 'string' && r.external_id) byId.set(r.external_id, r);
  }

  const rows: ExportRow[] = [];
  const used = new Set<string>();

  const rowFor = (a: ScannedAccount | null, read: CommenterAssessment | undefined): ExportRow => ({
    handle: (a?.handle ?? read?.handle ?? read?.ref ?? '').trim(),
    account_id: a?.external_id ?? read?.external_id ?? '',
    omi_score: clampScore(read?.omi_score),
    tier: read?.suspicion_tier ?? '',
    engine_tier: a?.tier ?? '',
    engine_score:
      typeof a?.probability === 'number' ? Math.round(a.probability * 100) : null,
    followers: typeof read?.follower_count === 'number' ? read.follower_count : null,
    following: typeof read?.following_count === 'number' ? read.following_count : null,
    account_created: read?.account_created_at ?? '',
    account_age_days: ageDays(read?.account_created_at, now),
    posts: typeof read?.post_count === 'number' ? read.post_count : null,
    intent: a?.intent_label ?? '',
    confidence: typeof read?.confidence === 'number' ? read.confidence : null,
    signals: signalMap(read?.signals),
    assessment: (read?.assessment ?? '').trim(),
  });

  for (const a of scanned) {
    const read = byId.get(a.external_id);
    if (read) used.add(a.external_id);
    rows.push(rowFor(a, read));
  }
  // An analyst read whose account is not in the engine list. Not expected, but dropping it silently
  // would delete a scored claim from the export while leaving it on the page.
  for (const [id, read] of byId) {
    if (!used.has(id)) rows.push(rowFor(null, read));
  }

  rows.sort((x, y) => (y.omi_score ?? y.engine_score ?? -1) - (x.omi_score ?? x.engine_score ?? -1));
  return rows;
}

type Column = { key: string; value: (r: ExportRow) => string | number | null };

const BASE_COLUMNS: Column[] = [
  { key: 'handle', value: (r) => r.handle },
  { key: 'account_id', value: (r) => r.account_id },
  { key: 'omi_score', value: (r) => r.omi_score },
  { key: 'tier', value: (r) => r.tier },
  { key: 'engine_tier', value: (r) => r.engine_tier },
  { key: 'engine_score', value: (r) => r.engine_score },
  { key: 'followers', value: (r) => r.followers },
  { key: 'following', value: (r) => r.following },
  { key: 'account_created', value: (r) => r.account_created },
  { key: 'account_age_days', value: (r) => r.account_age_days },
  { key: 'posts', value: (r) => r.posts },
  { key: 'intent', value: (r) => r.intent },
];

/**
 * The columns these rows actually carry.
 *
 * `confidence` and the eight signal columns appear only when the data has them, which is the same
 * thing as saying "only for an admin, until the breakdown ships". Asking the data rather than
 * re-deciding who may see what is what keeps this from becoming a second copy of the gate that has
 * to be remembered on the day the feature is released.
 *
 * `assessment` is last on purpose: it is the one free-text column, and a paragraph in the middle of
 * a table makes every column after it unreadable at default width.
 */
export function exportColumns(rows: ExportRow[]): Column[] {
  const hasSignals = rows.some((r) => r.signals !== null);
  const hasConfidence = rows.some((r) => r.confidence !== null);
  return [
    ...BASE_COLUMNS,
    ...(hasConfidence ? [{ key: 'confidence', value: (r: ExportRow) => r.confidence }] : []),
    ...(hasSignals
      ? ACCOUNT_SIGNAL_KEYS.map((k) => ({
          key: `signal_${k}`,
          value: (r: ExportRow) => (r.signals ? r.signals[k] ?? null : null),
        }))
      : []),
    { key: 'assessment', value: (r: ExportRow) => r.assessment },
  ];
}

function csvCell(value: string | number | null): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function tsvCell(value: string | number | null): string {
  if (value === null || value === undefined) return '';
  // TSV has no quoting: a spreadsheet splits a pasted block on tabs and newlines, so a verdict
  // containing either would explode into extra cells and extra rows. Collapse instead. CSV keeps the
  // text intact because quoting can carry it.
  return String(value).replace(/\s+/g, ' ').trim();
}

/**
 * What the numbers are and are not, carried with the file.
 *
 * The rest of the product states this above the verdict (the shared report, the markdown export,
 * `/accuracy`), and a spreadsheet of scored claims about named people is the same kind of artifact:
 * it gets forwarded, and whoever opens it did not see the page it came from.
 *
 * It goes at the BOTTOM, after a blank line, each line prefixed with `#`. A preamble would push the
 * header row off row 1, and a CSV whose first row is not its header breaks sorting, filtering, and
 * every tool that reads one. This costs a stray row at the end and nothing else.
 */
const SCOPE_FOOTER = [
  'These scores are probabilistic readings of public behaviour, not findings of fact.',
  'They describe how closely an account\'s public activity resembles patterns associated with bought or automated engagement.',
  'They are not an allegation that anyone broke a law or a platform rule, and they make no claim about who operates an account, whether money changed hands, or anyone\'s intent.',
  'Automated analysis is wrong sometimes, in both directions: businesses, fan accounts, news feeds, new users, and people writing in a second language can all resemble these patterns.',
  'omi_score is the analyst\'s per-account reading, 0-100. engine_score is the detection engine\'s own probability as a percentage. A blank omi_score means the account was scanned but not assessed.',
  'Full policy: /accuracy',
];

/**
 * RFC 4180 CSV, CRLF line endings, header on the first row.
 *
 * The leading U+FEFF is not decoration: Excel on Windows reads a UTF-8 file without a byte order
 * mark as the local ANSI codepage, which mangles every non-Latin handle in the export. Those are
 * common in this data and the protocol explicitly treats a non-Latin script as ordinary.
 */
export function toCsv(rows: ExportRow[]): string {
  const cols = exportColumns(rows);
  const lines = [cols.map((c) => csvCell(c.key)).join(',')];
  for (const r of rows) lines.push(cols.map((c) => csvCell(c.value(r))).join(','));
  lines.push('');
  for (const line of SCOPE_FOOTER) lines.push(csvCell(`# ${line}`));
  return '﻿' + lines.join('\r\n') + '\r\n';
}

/** Tab-separated, for the clipboard: pasting this into Sheets, Excel or Notion lands as real
 *  columns, where pasting CSV lands as one column per row and has to be split by hand. */
export function toTsv(rows: ExportRow[]): string {
  const cols = exportColumns(rows);
  const lines = [cols.map((c) => c.key).join('\t')];
  for (const r of rows) lines.push(cols.map((c) => tsvCell(c.value(r))).join('\t'));
  return lines.join('\n');
}

/** A filename that still says what it is after it has been sitting in a downloads folder. */
export function exportFilename(slug: string, createdAt?: string): string {
  const safe = (slug || 'investigation').replace(/[^a-zA-Z0-9._-]+/g, '-').slice(0, 60);
  const day = createdAt && !Number.isNaN(Date.parse(createdAt))
    ? new Date(createdAt).toISOString().slice(0, 10)
    : '';
  return `omisphere-${safe}${day ? `-${day}` : ''}-accounts.csv`;
}
