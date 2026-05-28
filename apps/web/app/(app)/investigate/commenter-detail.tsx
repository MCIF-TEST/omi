import Link from 'next/link';
import { TrendingUp, AlertTriangle, MessageSquareText, ArrowRight, BarChart2, ShieldAlert } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { type CommenterScanResult, type SignalResult } from '@/lib/api';
import { timeAgo } from '@/lib/format';

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

  return (
    <article className="space-y-5 p-5">
      {/* Header */}
      <header>
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <TierBadge tier={c.tier} size="lg" />
          {c.from_cache && (
            <span className="font-mono text-2xs tracking-wider text-fg-mute uppercase">[cached]</span>
          )}
          {c.matched_prior_neighbors > 0 && (
            <span className="font-mono text-2xs tracking-wider text-accent uppercase">
              {c.matched_prior_neighbors} prior neighbor{c.matched_prior_neighbors === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <h2 className="text-xl font-semibold text-fg tracking-tight mb-0.5">
          {c.handle || c.external_id}
        </h2>
        {c.display_name && <p className="text-sm text-fg-dim">{c.display_name}</p>}
        <p className="font-mono text-2xs text-fg-faint mt-1 break-all">{c.external_id}</p>
      </header>

      {/* Probability */}
      <section>
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Inauthentic probability
          </span>
          <span className="text-3xl font-bold mono text-fg tracking-tight">
            {Math.round(displayProb * 100)}%
          </span>
        </div>
        <ProbabilityBar value={displayProb} tier={c.tier} showLabel={false} />
        {showAdjusted && (
          <p className="mt-2 text-xs text-accent font-mono">
            ↑ adjusted from {Math.round(c.overall_probability * 100)}% via coordination cluster
          </p>
        )}
        <p className="mt-2 text-sm text-fg-dim leading-relaxed">{c.summary}</p>
      </section>

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

      {/* Activity sample */}
      {isFlagged && (c.recent_activity ?? []).length > 0 && (
        <section>
          <Label
            icon={<MessageSquareText size={11} />}
            text={`Activity — showing ${c.recent_activity.length} of ${c.activity_total}`}
          />
          <div className="space-y-2">
            {(c.recent_activity ?? []).map((a, i) => (
              <div key={i} className="bg-bg border border-border-1 rounded-sm p-3">
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
        </section>
      )}

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
          className="flex items-center justify-between gap-2 px-3 py-2.5 rounded-sm bg-bg border border-border-1 hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors"
        >
          <div>
            <p className="font-mono text-2xs tracking-wider uppercase text-accent mb-0.5">
              View account profile
            </p>
            <p className="text-xs text-fg-dim">
              AI behavioural analysis · signal breakdown · scan history
            </p>
          </div>
          <ArrowRight size={14} className="text-fg-mute shrink-0" />
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
