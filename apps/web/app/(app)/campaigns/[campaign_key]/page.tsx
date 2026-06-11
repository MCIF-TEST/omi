import Link from 'next/link';
import { notFound } from 'next/navigation';
import {
  Megaphone, Network, ShieldCheck, AlertTriangle, Clock, Activity,
  Crosshair, ArrowRight, Hash, AtSign, ChevronLeft, FileText, Download,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import {
  type CampaignDetail,
  type CampaignObservationOut,
  DISCRIMINATIVE_DETECTORS,
  isCorroborated,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { ApiError } from '@/lib/api';
import { timeAgo } from '@/lib/format';
import { CampaignShareBlock } from './share-block';

export const metadata = { title: 'Campaign — OMISPHERE' };
export const dynamic = 'force-dynamic';

const KNOWN_METHODS = [
  'fingerprint_cluster',
  'co_engagement',
  'co_tag',
  'style_match',
  'temporal_semantic_clique',
  'age_cohort',
] as const;

const METHOD_LABEL: Record<string, string> = {
  fingerprint_cluster:       'Fingerprint cluster',
  co_engagement:             'Co-engagement',
  co_tag:                    'Co-tag / co-mention',
  style_match:               'Style match',
  temporal_semantic_clique:  'Temporal-semantic',
  age_cohort:                'Account-age cohort',
};

const METHOD_RATIONALE_WHEN_SILENT: Record<string, string> = {
  fingerprint_cluster:      'no shared behavioral fingerprint detected',
  co_engagement:            'no overlapping engagement history available',
  co_tag:                   'no shared hashtag / mention pattern observed',
  style_match:              'stylometric features did not cluster',
  temporal_semantic_clique: 'no synchronized comment-burst observed',
  age_cohort:               'account creation dates not clustered',
};

interface PageProps {
  params: { campaign_key: string };
  searchParams?: { ref?: string };
}

export default async function CampaignDetailPage({ params, searchParams }: PageProps) {
  // Forward the navigation-source marker so the backend can log
  // featured_viewed with its origin (founder-learning Q1 diagnostic).
  const ref = searchParams?.ref === 'featured' ? '?ref=featured' : '';
  let detail: CampaignDetail;
  try {
    detail = await apiServer<CampaignDetail>(`/v1/campaigns/${params.campaign_key}${ref}`);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    throw err;
  }

  const corroborated = isCorroborated(detail.methods);
  const methodsFired = new Set(detail.methods);
  const methodsSilent = KNOWN_METHODS.filter((m) => !methodsFired.has(m));
  const discriminativeFired = detail.methods.filter((m) =>
    DISCRIMINATIVE_DETECTORS.has(m),
  );

  return (
    <div className="space-y-6 pb-12">
      {/* Breadcrumb */}
      <div>
        <Link
          href="/campaigns"
          className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-mute hover:text-fg"
        >
          <ChevronLeft size={12} />
          All campaigns
        </Link>
      </div>

      {/* Featured-example context — a worked example is framed as such so it
          can never be mistaken for the user's own scan output. */}
      {detail.campaign_key.startsWith('feat_') && (
        <div className="flex items-start gap-2.5 border border-accent/25 bg-accent/[0.05] rounded-md px-4 py-3">
          <Megaphone size={14} className="text-accent mt-0.5 shrink-0" />
          <p className="text-sm text-fg-dim leading-relaxed">
            <span className="text-accent font-mono text-2xs uppercase tracking-wider mr-2">Featured example</span>
            A real influence operation from the platform&apos;s own disclosure
            archives, seeded so you can explore how Omi reads coordination.
            Your own scans appear alongside —{' '}
            <Link href="/investigate" className="text-accent hover:underline">run one now</Link>.
          </p>
        </div>
      )}

      {/* Header */}
      <div>
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <Megaphone size={18} className="text-accent" />
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">
            Campaign · {detail.platform} · {detail.member_count} accounts
          </span>
          <StatusPill status={detail.status} />
          {!corroborated && (
            <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-tier-moderate/40 bg-tier-moderate/10 text-tier-moderate">
              <AlertTriangle size={10} />
              supporting only
            </span>
          )}
        </div>
        <h1 className="text-2xl font-semibold tracking-tight leading-tight">
          {detail.name}
        </h1>
        <p className="text-sm text-fg-mute mt-1 font-mono">
          first detected {timeAgo(detail.first_detected_at)} · last seen{' '}
          {timeAgo(detail.last_seen_at)} · {detail.observation_count}×
        </p>
      </div>

      {/* Hero — score / confidence / corroboration. NEVER one number on its own. */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <HeroPanel
          label="Coordination"
          headline={`${Math.round(detail.max_coordination_score * 100)}%`}
          tone={
            !corroborated ? 'moderate'
              : detail.max_coordination_score >= 0.75 ? 'high'
              : 'elevated'
          }
          sub={`now ${Math.round(detail.coordination_score * 100)}%`}
          rightLabel="max observed"
        />
        <HeroPanel
          label="Confidence"
          headline={`${Math.round(detail.confidence * 100)}%`}
          tone={detail.confidence >= 0.7 ? 'ok' : detail.confidence >= 0.4 ? 'moderate' : 'mute'}
          sub={
            detail.confidence >= 0.7 ? 'high — independent detectors agree'
              : detail.confidence >= 0.4 ? 'moderate'
              : 'low — thin evidence'
          }
          rightLabel={`${detail.methods.length} method${detail.methods.length === 1 ? '' : 's'}`}
        />
        <HeroPanel
          label="Corroboration"
          headline={corroborated ? `${detail.methods.length} agree` : '1 supporting only'}
          tone={corroborated ? 'ok' : 'moderate'}
          sub={
            discriminativeFired.length > 0
              ? `${discriminativeFired.length} discriminative`
              : 'no discriminative detector fired'
          }
          icon={corroborated ? <ShieldCheck size={14} /> : <AlertTriangle size={14} />}
          rightLabel="phase-3 gate"
        />
      </div>

      {/* Gate banner */}
      {!corroborated && (
        <Card>
          <div className="flex items-start gap-3">
            <div className="shrink-0 mt-0.5 w-8 h-8 rounded-md bg-tier-moderate/15 text-tier-moderate flex items-center justify-center">
              <AlertTriangle size={16} />
            </div>
            <div>
              <div className="font-mono text-2xs uppercase tracking-wider text-tier-moderate mb-1">
                supporting evidence only
              </div>
              <p className="text-sm text-fg-dim leading-relaxed">
                Only one non-discriminative detector (
                {detail.methods.join(', ') || '—'}
                ) fired on this group. Under the Phase-3 corroboration gate,
                the score is capped at MODERATE — the same fix that took
                campaign-level FPR on legitimate-coordination controls to
                zero. The cluster is real; the interpretation is not yet
                confirmed.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Evidence pack — the citable, portable artifact (carries the trust */}
      {/* contract: corroboration status, evidence-for/against, methodology, */}
      {/* and the observation-not-verdict disclaimer travel with the file). */}
      <ExportBlock campaignKey={detail.campaign_key} corroborated={corroborated} />

      {/* Public report — revocable, token-gated, read-only link for distribution. */}
      <CampaignShareBlock campaignKey={detail.campaign_key} initialToken={detail.share_token} />

      {/* Evidence for / against — side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <EvidenceForPanel detail={detail} />
        <EvidenceAgainstPanel
          silentMethods={methodsSilent}
          observations={detail.observations}
          coordination_score={detail.coordination_score}
          max_coordination_score={detail.max_coordination_score}
        />
      </div>

      {/* Tags & targets */}
      {(detail.hashtags.length > 0 || detail.mentions.length > 0) && (
        <Card>
          <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-3">
            Tags &amp; targets
          </div>
          <div className="flex flex-wrap gap-1.5">
            {detail.hashtags.map((h) => (
              <span
                key={`#${h}`}
                className="inline-flex items-center gap-1 font-mono text-xs px-2 py-1 rounded-sm bg-bg-elev-2 border border-border-1 text-fg-dim"
              >
                <Hash size={10} className="text-fg-mute" />
                {h.replace(/^#/, '')}
              </span>
            ))}
            {detail.mentions.map((m) => (
              <span
                key={`@${m}`}
                className="inline-flex items-center gap-1 font-mono text-xs px-2 py-1 rounded-sm bg-bg-elev-2 border border-border-1 text-fg-dim"
              >
                <AtSign size={10} className="text-fg-mute" />
                {m.replace(/^@/, '')}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Members */}
      <Card>
        <div className="flex items-center justify-between mb-3">
          <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute flex items-center gap-1.5">
            <Network size={12} />
            Members
          </div>
          <span className="font-mono text-2xs text-fg-faint">
            {detail.members.length} of {detail.member_count}
          </span>
        </div>
        {detail.members.length === 0 ? (
          <p className="text-sm text-fg-mute">No member rows captured yet.</p>
        ) : (
          <div className="overflow-x-auto -mx-4 px-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left font-mono text-2xs uppercase tracking-wider text-fg-faint border-b border-border-1">
                  <th className="py-2 pr-3">Account</th>
                  <th className="py-2 pr-3 text-right">Times</th>
                  <th className="py-2 pr-3">Methods</th>
                  <th className="py-2 pl-3 text-right" aria-label="navigate" />
                </tr>
              </thead>
              <tbody>
                {detail.members.map((m) => (
                  <tr key={m.account_external_id} className="border-b border-border-1/60 last:border-0">
                    <td className="py-2 pr-3">
                      <Link
                        href={`/accounts/${encodeURIComponent(m.account_external_id)}`}
                        className="text-fg hover:text-accent"
                      >
                        {m.handle || m.account_external_id}
                      </Link>
                    </td>
                    <td className="py-2 pr-3 text-right font-mono tabular-nums text-fg-dim">
                      {m.times_observed}×
                    </td>
                    <td className="py-2 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {m.methods.map((mt) => (
                          <MethodChip key={mt} method={mt} />
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pl-3 text-right text-fg-mute">
                      <ArrowRight size={14} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Recurrence timeline */}
      <Card>
        <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-3 flex items-center gap-1.5">
          <Clock size={12} />
          Recurrence timeline
        </div>
        {detail.observations.length === 0 ? (
          <p className="text-sm text-fg-mute">No observation history.</p>
        ) : (
          <ol className="space-y-3">
            {detail.observations.map((o, i) => {
              const prev = detail.observations[i + 1]; // observations are newest-first
              return (
                <ObservationRow
                  key={`${o.observed_at}-${i}`}
                  obs={o}
                  prev={prev}
                  isLatest={i === 0}
                />
              );
            })}
          </ol>
        )}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-panels — inline (matches narrative idiom).
// ---------------------------------------------------------------------------

function ExportBlock({
  campaignKey, corroborated,
}: { campaignKey: string; corroborated: boolean }) {
  // Plain download anchors hit the same-origin /api rewrite, which carries the
  // auth cookie; the endpoint's Content-Disposition triggers the download.
  // No client state needed — mirrors the investigation share/export idiom.
  const base = `/api/v1/campaigns/${encodeURIComponent(campaignKey)}/export`;
  return (
    <Card>
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-1 flex items-center gap-1.5">
            <FileText size={12} />
            Evidence pack
          </div>
          <p className="text-sm text-fg-dim max-w-xl">
            Download a citable record of this campaign — members, methods,
            evidence for and against, recurrence, and the corroboration status —
            with the methodology and the &ldquo;observation, not verdict&rdquo;
            framing included{corroborated ? '' : ' (this campaign is flagged supporting-only)'}.
            Markdown for a report; JSON for archival or tooling.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <a
            href={`${base}?format=markdown`}
            className="inline-flex items-center gap-1.5 px-3 h-9 border border-accent-dim bg-accent/10 text-accent rounded-sm font-mono text-xs tracking-wider uppercase hover:bg-accent/20"
          >
            <FileText size={12} /> Markdown
          </a>
          <a
            href={`${base}?format=json`}
            className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
          >
            <Download size={12} /> JSON
          </a>
        </div>
      </div>
    </Card>
  );
}

function EvidenceForPanel({ detail }: { detail: CampaignDetail }) {
  return (
    <Card>
      <div className="font-mono text-2xs uppercase tracking-wider text-accent mb-3 flex items-center gap-1.5">
        <Activity size={12} />
        Evidence for
      </div>
      <ul className="space-y-2.5">
        {detail.methods.length === 0 ? (
          <li className="text-sm text-fg-mute">No detectors fired.</li>
        ) : (
          detail.methods.map((m) => (
            <li key={m} className="flex items-start gap-2">
              <span className="shrink-0 mt-0.5">
                <ShieldCheck
                  size={14}
                  className={DISCRIMINATIVE_DETECTORS.has(m) ? 'text-accent' : 'text-fg-mute'}
                />
              </span>
              <div className="text-sm">
                <div className="text-fg">
                  {METHOD_LABEL[m] || m}
                  {DISCRIMINATIVE_DETECTORS.has(m) && (
                    <span className="ml-2 font-mono text-2xs uppercase tracking-wider text-accent">
                      discriminative
                    </span>
                  )}
                </div>
              </div>
            </li>
          ))
        )}
      </ul>
      {detail.evidence.length > 0 && (
        <ul className="mt-3 pt-3 border-t border-border-1 space-y-1.5 text-sm text-fg-dim">
          {detail.evidence.slice(0, 6).map((e, i) => (
            <li key={i} className="leading-snug">
              <span className="text-fg-faint">·</span> {e}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function EvidenceAgainstPanel({
  silentMethods, observations, coordination_score, max_coordination_score,
}: {
  silentMethods: readonly string[];
  observations: CampaignObservationOut[];
  coordination_score: number;
  max_coordination_score: number;
}) {
  const weakening =
    observations.length >= 2 && coordination_score < max_coordination_score - 0.05;
  return (
    <Card>
      <div className="font-mono text-2xs uppercase tracking-wider text-tier-moderate mb-3 flex items-center gap-1.5">
        <AlertTriangle size={12} />
        Evidence weakening
      </div>
      <ul className="space-y-2.5 text-sm">
        {silentMethods.length === 0 && !weakening ? (
          <li className="text-fg-mute">No counter-evidence surfaced.</li>
        ) : (
          <>
            {silentMethods.map((m) => (
              <li key={m} className="flex items-start gap-2 text-fg-dim">
                <span className="shrink-0 mt-0.5 text-fg-faint">·</span>
                <div>
                  <span className="text-fg-mute">{METHOD_LABEL[m] || m}:</span>{' '}
                  {METHOD_RATIONALE_WHEN_SILENT[m] || 'detector did not fire'}
                </div>
              </li>
            ))}
            {weakening && (
              <li className="flex items-start gap-2 text-tier-moderate">
                <Crosshair size={12} className="shrink-0 mt-1" />
                <div>
                  Trend: weakening. Latest score{' '}
                  {Math.round(coordination_score * 100)}% is below the campaign
                  max of {Math.round(max_coordination_score * 100)}% — recent
                  observations were less coordinated than earlier ones.
                </div>
              </li>
            )}
          </>
        )}
      </ul>
    </Card>
  );
}

function ObservationRow({
  obs, prev, isLatest,
}: {
  obs: CampaignObservationOut;
  prev: CampaignObservationOut | undefined;
  isLatest: boolean;
}) {
  const scorePct = Math.round(obs.coordination_score * 100);
  const memberDiff = prev ? obs.member_count - prev.member_count : 0;
  const newMethods = prev
    ? obs.methods.filter((m) => !prev.methods.includes(m))
    : [];

  return (
    <li className="flex gap-3">
      <div className="flex flex-col items-center pt-1.5 shrink-0">
        <span
          className={`w-2.5 h-2.5 rounded-full ${
            isLatest ? 'bg-accent' : 'bg-border-2'
          }`}
        />
        {!isLatest && <span className="flex-1 w-px bg-border-1 mt-1" />}
      </div>
      <div className="flex-1 pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-dim">
            {new Date(obs.observed_at).toUTCString().slice(0, 22)}
          </span>
          <span className="font-mono text-2xs text-fg-mute">{timeAgo(obs.observed_at)}</span>
        </div>
        <div className="mt-1 flex items-center gap-3 text-sm">
          <span className="text-fg tabular-nums">{scorePct}% score</span>
          <span className="text-fg-mute">·</span>
          <span className="text-fg-dim">{obs.member_count} members</span>
          {memberDiff !== 0 && (
            <span className={memberDiff > 0 ? 'text-accent' : 'text-fg-mute'}>
              ({memberDiff > 0 ? '+' : ''}{memberDiff})
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap gap-1">
          {obs.methods.map((m) => (
            <MethodChip key={m} method={m} />
          ))}
        </div>
        {newMethods.length > 0 && (
          <div className="mt-1 font-mono text-2xs text-accent">
            + {newMethods.map((m) => METHOD_LABEL[m] || m).join(', ')} now firing
          </div>
        )}
      </div>
    </li>
  );
}

function MethodChip({ method }: { method: string }) {
  const discriminative = DISCRIMINATIVE_DETECTORS.has(method);
  const cls = discriminative
    ? 'border-accent/40 bg-accent/10 text-accent'
    : 'border-border-2 text-fg-mute';
  return (
    <span
      title={discriminative ? 'Discriminative detector' : 'Supporting detector'}
      className={`inline-flex items-center font-mono text-[0.6rem] tracking-wider uppercase px-1.5 py-0.5 rounded-sm border ${cls}`}
    >
      {METHOD_LABEL[method] || method}
    </span>
  );
}

function HeroPanel({
  label, headline, sub, tone, icon, rightLabel,
}: {
  label: string;
  headline: string;
  sub: string;
  tone: 'mute' | 'moderate' | 'elevated' | 'high' | 'ok';
  icon?: React.ReactNode;
  rightLabel?: string;
}) {
  const headlineCls = {
    mute:     'text-fg',
    moderate: 'text-tier-moderate',
    elevated: 'text-tier-elevated',
    high:     'text-tier-high',
    ok:       'text-accent',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute flex items-center gap-1.5">
          {icon} {label}
        </span>
        {rightLabel && (
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-faint">
            {rightLabel}
          </span>
        )}
      </div>
      <div className={`text-3xl font-semibold tabular-nums ${headlineCls}`}>{headline}</div>
      <div className="mt-1 text-xs text-fg-mute">{sub}</div>
    </div>
  );
}

function StatusPill({ status }: { status: 'observed' | 'recurring' }) {
  if (status === 'recurring') {
    return (
      <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-accent/40 bg-accent/10 text-accent">
        <Clock size={10} />
        recurring
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute">
      observed
    </span>
  );
}
