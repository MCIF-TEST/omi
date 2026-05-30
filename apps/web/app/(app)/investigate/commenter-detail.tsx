'use client';

import { useState } from 'react';
import Link from 'next/link';
import { TrendingUp, AlertTriangle, MessageSquareText, ArrowRight, BarChart2, ShieldAlert, Radar, Loader2 } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { ScoreRing } from '@/components/shared/score-ring';
import { CommenterThreatPanel } from '@/components/shared/commenter-threat-panel';
import { apiClient, ApiError, type AccountScanOut, type CommenterScanResult, type SignalResult } from '@/lib/api';
import { timeAgo } from '@/lib/format';

type ActivitySample = CommenterScanResult['recent_activity'][number];

const SIGNAL_LABELS: Record<string, string> = {
  temporal:    'Posting cadence',
  semantic:    'Content repetition',
  ai_writing:  'AI-writing patterns',
  profile:     'Profile metadata',
  voice:       'Personal voice',
  engagement:  'Engagement farming',
  memory:      'Fingerprint match',
  coordination:'Coordination cluster',
};

export function CommenterDetail({ c }: { c: CommenterScanResult }) {
  const adjusted = c.coordination_adjusted_probability;
  const displayProb = adjusted ?? c.overall_probability ?? 0;
  const showAdjusted = adjusted != null && Math.abs(adjusted - c.overall_probability) > 0.005;
  const isFlagged = c.tier !== 'low';
  const signals = (c.signals ?? []).filter((s) => s.confidence > 0);

  // On-demand deep scan of THIS commenter: pulls their recent comment history
  // (and a fresh score) via the single-account scan, so the operator can see
  // what an account has actually been commenting — even for low-tier or cached
  // commenters whose history wasn't bundled into the bulk scan.
  const [deep, setDeep] = useState<{
    loading: boolean;
    error: string | null;
    activity: ActivitySample[] | null;
    total: number;
  }>({ loading: false, error: null, activity: null, total: 0 });

  const runDeepScan = async () => {
    setDeep((d) => ({ ...d, loading: true, error: null }));
    try {
      const res = await apiClient<AccountScanOut>('/v1/scan/youtube/account', {
        method: 'POST',
        body: JSON.stringify({ account_url_or_handle: c.external_id, force_refresh: true }),
      });
      setDeep({
        loading: false,
        error: null,
        activity: res.recent_activity ?? [],
        total: res.activity_total ?? (res.recent_activity?.length ?? 0),
      });
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.status === 402 ? 'Out of credits — visit Settings to subscribe.'
          : e.status === 401 ? 'Please log in to scan.'
          : e.message
          : e instanceof Error && e.message ? e.message
          : 'Scan failed. Try again.';
      setDeep((d) => ({ ...d, loading: false, error: msg }));
    }
  };

  // Prefer freshly-pulled history; fall back to whatever the bulk scan bundled.
  const activity = deep.activity ?? c.recent_activity ?? [];
  const activityTotal = deep.activity ? deep.total : c.activity_total;

  return (
    <article className="space-y-5 p-5">
      {/* Hero — score ring + identity */}
      <header className="relative overflow-hidden rounded-2xl border border-border-1 bg-gradient-to-br from-bg-elev-2/60 to-bg-elev/20 p-5">
        <div className="absolute -top-12 -right-10 w-40 h-40 rounded-full bg-accent/[0.06] blur-3xl pointer-events-none" aria-hidden />
        <div className="relative flex items-start gap-5 flex-wrap">
          <div className="flex flex-col items-center gap-2 shrink-0">
            <ScoreRing value={displayProb} tier={c.tier} size={88} stroke={7} />
            <span className="font-mono text-[0.6rem] tracking-[0.16em] text-fg-mute uppercase">
              inauthentic
            </span>
          </div>
          <div className="flex-1 min-w-[180px]">
            <div className="flex items-center gap-2 flex-wrap mb-2">
              <TierBadge tier={c.tier} size="lg" />
              {c.from_cache && (
                <span className="font-mono text-2xs tracking-wider text-fg-mute uppercase border border-border-2 rounded-full px-2 py-0.5">cached</span>
              )}
              {c.matched_prior_neighbors > 0 && (
                <span className="font-mono text-2xs tracking-wider text-accent uppercase border border-accent/30 bg-accent/10 rounded-full px-2 py-0.5">
                  {c.matched_prior_neighbors} prior neighbor{c.matched_prior_neighbors === 1 ? '' : 's'}
                </span>
              )}
            </div>
            <h2 className="display text-xl font-semibold text-fg tracking-tight mb-0.5 break-words">
              {c.handle || c.external_id}
            </h2>
            {c.display_name && <p className="text-sm text-fg-dim">{c.display_name}</p>}
            <p className="font-mono text-2xs text-fg-faint mt-1 break-all">{c.external_id}</p>
          </div>
        </div>
        {showAdjusted && (
          <p className="relative mt-3 text-xs text-accent font-mono flex items-center gap-1.5">
            <TrendingUp size={12} />
            adjusted from {Math.round(c.overall_probability * 100)}% via coordination cluster
          </p>
        )}
        <p className="relative mt-3 text-sm text-fg-dim leading-relaxed">{c.summary}</p>
      </header>

      {/* OmiScore intelligence — composed, explainable threat verdict */}
      <CommenterThreatPanel platform={c.platform || 'youtube'} externalId={c.external_id} />

      {/* Per-detector signal breakdown */}
      {signals.length > 0 && (
        <section>
          <Label icon={<BarChart2 size={11} />} text="Detector breakdown" />
          <div className="space-y-2">
            {signals.map((s) => (
              <SignalRow key={s.name} signal={s} />
            ))}
          </div>
        </section>
      )}

      {/* Suspected intent */}
      {isFlagged && c.intent_label && (
        <section>
          <Label icon={<ShieldAlert size={11} />} text="Suspected intent" />
          <p className="text-sm text-fg">{c.intent_label}</p>
        </section>
      )}

      {/* Reasons */}
      {isFlagged && (c.reasons ?? []).length > 0 && (
        <section>
          <Label icon={<TrendingUp size={11} />} text="Why this account was flagged" />
          <ul className="space-y-1.5">
            {(c.reasons ?? []).map((r, i) => (
              <li key={i} className="text-sm text-fg leading-relaxed pl-3 border-l border-border-2">
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Comment history — what this account has actually been commenting.
          Omi bundles a sample on the bulk scan for flagged accounts; the
          button pulls (or refreshes) the full recent history on demand for
          anyone, including low-tier or cached commenters. */}
      <section>
        <div className="flex items-center justify-between gap-2 mb-2">
          <Label
            icon={<MessageSquareText size={11} />}
            text={
              activity.length > 0
                ? `Comment history — showing ${activity.length} of ${activityTotal}`
                : 'Comment history'
            }
          />
          <button
            type="button"
            onClick={runDeepScan}
            disabled={deep.loading}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-sm border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 font-mono text-2xs uppercase tracking-wider transition-colors disabled:opacity-50 shrink-0"
            title="Pull this account's recent comments from YouTube (uses 1 credit)"
          >
            {deep.loading ? (
              <><Loader2 size={11} className="animate-spin" /> Scanning…</>
            ) : (
              <><Radar size={11} /> {activity.length > 0 ? 'Rescan history' : 'Scan history'}</>
            )}
          </button>
        </div>

        {deep.error && (
          <p className="text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono mb-2">
            {deep.error}
          </p>
        )}

        {activity.length > 0 ? (
          <div className="space-y-2">
            {activity.map((a, i) => (
              <div key={i} className="bg-bg border border-border-1 rounded-xl p-3 hover:border-border-hot/60 transition-colors">
                <p className="text-sm text-fg leading-relaxed break-words">{a.text}</p>
                <div className="mt-2 flex items-center justify-between gap-2 font-mono text-2xs tracking-wider uppercase text-fg-mute">
                  <span>{a.created_at ? timeAgo(a.created_at) : '—'}</span>
                  {a.parent_id && (
                    <a
                      href={`https://youtube.com/watch?v=${a.parent_id}`}
                      target="_blank"
                      rel="noopener"
                      className="text-accent hover:text-accent-2 inline-flex items-center gap-1"
                    >
                      on video <ArrowRight size={10} />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          !deep.loading && (
            <p className="text-xs text-fg-mute leading-relaxed">
              No comments pulled yet. Scan to fetch this account&apos;s recent
              comment history from YouTube.
            </p>
          )
        )}
      </section>

      {/* Coordination evidence */}
      {(c.coordination_evidence ?? []).length > 0 && (
        <section>
          <Label icon={<AlertTriangle size={11} />} text="Coordination evidence" />
          <ul className="space-y-1.5">
            {(c.coordination_evidence ?? []).map((e, i) => (
              <li key={i} className="text-sm text-fg-dim leading-relaxed pl-3 border-l border-tier-elevated/50">
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Data quality caveats */}
      {(c.weak_signals ?? []).length > 0 && (
        <section>
          <Label text="Data-quality caveats" />
          <ul className="space-y-1 text-xs text-fg-mute">
            {(c.weak_signals ?? []).map((w, i) => (
              <li key={i}>· {w}</li>
            ))}
          </ul>
        </section>
      )}

      {c.error && (
        <p className="text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          Scan error: {c.error}
        </p>
      )}

      {/* Account profile link */}
      <div className="pt-1 border-t border-border-1">
        <Link
          href={`/accounts/${encodeURIComponent(c.external_id)}?platform=${c.platform || 'youtube'}`}
          className="group flex items-center justify-between gap-2 px-4 py-3 rounded-xl bg-bg border border-border-1 hover:border-accent/40 hover:bg-accent/[0.04] transition-all"
        >
          <div>
            <p className="font-mono text-2xs tracking-wider uppercase text-accent mb-0.5">
              View account profile
            </p>
            <p className="text-xs text-fg-dim">
              AI behavioural analysis · signal breakdown · scan history
            </p>
          </div>
          <ArrowRight size={14} className="text-fg-mute shrink-0 group-hover:text-accent group-hover:translate-x-0.5 transition-all" />
        </Link>
      </div>
    </article>
  );
}

function SignalRow({ signal }: { signal: SignalResult }) {
  const prob = signal.probability ?? 0;
  const conf = signal.confidence ?? 0;
  const label = SIGNAL_LABELS[signal.name] ?? signal.name;
  const topEvidence = signal.evidence?.[0];

  const barColor =
    prob >= 0.75 ? 'bg-tier-high' :
    prob >= 0.5  ? 'bg-tier-elevated' :
    prob >= 0.25 ? 'bg-tier-moderate' :
    'bg-tier-low';

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-mono text-fg-dim uppercase tracking-wider text-2xs">{label}</span>
        <div className="flex items-center gap-2 shrink-0">
          <span className="font-mono text-fg-mute text-2xs">
            conf {Math.round(conf * 100)}%
          </span>
          <span className={`font-mono font-semibold ${
            prob >= 0.75 ? 'text-tier-high' :
            prob >= 0.5  ? 'text-tier-elevated' :
            prob >= 0.25 ? 'text-tier-moderate' :
            'text-tier-low'
          }`}>
            {Math.round(prob * 100)}%
          </span>
        </div>
      </div>
      {/* Probability bar */}
      <div className="h-1 w-full bg-border-1 rounded-full overflow-hidden mb-1">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${Math.round(prob * 100)}%`, opacity: Math.max(0.3, conf) }}
        />
      </div>
      {topEvidence && conf > 0.1 && (
        <p className="text-fg-mute leading-relaxed">{topEvidence}</p>
      )}
    </div>
  );
}

function Label({ icon, text }: { icon?: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-2">
      {icon}{text}
    </div>
  );
}
