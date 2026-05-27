import Link from 'next/link';
import { TrendingUp, AlertTriangle, MessageSquareText, ArrowRight } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { type CommenterScanResult } from '@/lib/api';
import { timeAgo } from '@/lib/format';

export function CommenterDetail({ c }: { c: CommenterScanResult }) {
  const adjusted = c.coordination_adjusted_probability;
  const displayProb = adjusted ?? c.overall_probability ?? 0;
  const showAdjusted = adjusted != null && Math.abs(adjusted - c.overall_probability) > 0.005;
  const isFlagged = c.tier !== 'low';

  return (
    <article className="space-y-6 p-6">
      <header>
        <div className="flex items-center gap-3 flex-wrap mb-3">
          <TierBadge tier={c.tier} size="lg" />
          {c.from_cache && (
            <span className="font-mono text-2xs tracking-wider text-fg-mute uppercase">
              [cached]
            </span>
          )}
          {c.matched_prior_neighbors > 0 && (
            <span className="font-mono text-2xs tracking-wider text-accent uppercase">
              {c.matched_prior_neighbors} prior neighbor{c.matched_prior_neighbors === 1 ? '' : 's'}
            </span>
          )}
        </div>
        <h2 className="text-xl font-semibold text-fg tracking-tight mb-1">
          {c.handle || c.external_id}
        </h2>
        {c.display_name && <p className="text-sm text-fg-dim">{c.display_name}</p>}
        <p className="font-mono text-2xs text-fg-faint mt-1 break-all">{c.external_id}</p>
      </header>

      {/* Probability + adjustment */}
      <section>
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Probability
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
        <p className="mt-3 text-sm text-fg-dim leading-relaxed">{c.summary}</p>
      </section>

      {/* Suspected intent */}
      {isFlagged && c.intent_label && (
        <section>
          <Label icon={<AlertTriangle size={11} />} text="Suspected intent" />
          <p className="text-sm text-fg">{c.intent_label}</p>
        </section>
      )}

      {/* Reasons */}
      {isFlagged && c.reasons.length > 0 && (
        <section>
          <Label icon={<TrendingUp size={11} />} text="Why this account was flagged" />
          <ul className="space-y-1.5">
            {c.reasons.map((r, i) => (
              <li key={i} className="text-sm text-fg leading-relaxed pl-3 border-l border-border-2">
                {r}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Activity sample */}
      {isFlagged && c.recent_activity.length > 0 && (
        <section>
          <Label
            icon={<MessageSquareText size={11} />}
            text={`Activity — showing ${c.recent_activity.length} of ${c.activity_total}`}
          />
          <div className="space-y-2">
            {c.recent_activity.map((a, i) => (
              <div
                key={i}
                className="bg-bg border border-border-1 rounded-sm p-3"
              >
                <p className="text-sm text-fg leading-relaxed break-words">{a.text}</p>
                <div className="mt-2 flex items-center justify-between gap-2 font-mono text-2xs tracking-wider uppercase text-fg-mute">
                  <span>{timeAgo(a.created_at)}</span>
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
      {c.coordination_evidence.length > 0 && (
        <section>
          <Label icon={<AlertTriangle size={11} />} text="Coordination evidence" />
          <ul className="space-y-1.5">
            {c.coordination_evidence.map((e, i) => (
              <li key={i} className="text-sm text-fg-dim leading-relaxed pl-3 border-l border-tier-elevated/50">
                {e}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Weak signals */}
      {c.weak_signals.length > 0 && (
        <section>
          <Label text="Data-quality caveats" />
          <ul className="space-y-1 text-xs text-fg-mute">
            {c.weak_signals.map((w, i) => (
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

      <div>
        <Link
          href={`/accounts/${encodeURIComponent(c.external_id)}?platform=${c.platform || 'youtube'}`}
          className="inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase text-accent hover:text-accent-2"
        >
          Open account history <ArrowRight size={11} />
        </Link>
      </div>
    </article>
  );
}

function Label({ icon, text }: { icon?: React.ReactNode; text: string }) {
  return (
    <div className="flex items-center gap-1.5 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-2">
      {icon}{text}
    </div>
  );
}
