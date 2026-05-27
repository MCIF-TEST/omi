import { Link2, AlertCircle } from 'lucide-react';
import { type CrossLink } from '@/lib/api';

const SEV_STYLE: Record<CrossLink['severity'], string> = {
  high:     'border-tier-high/50 bg-tier-high/10 text-tier-high',
  elevated: 'border-tier-elevated/50 bg-tier-elevated/10 text-tier-elevated',
  moderate: 'border-tier-moderate/50 bg-tier-moderate/10 text-tier-moderate',
  info:     'border-accent-dim bg-accent/10 text-accent',
};

const KIND_LABEL: Record<string, string> = {
  focus_in_video: 'In video',
  focus_in_cluster: 'In cluster',
  focus_resembles_cluster: 'FP near cluster',
  fellow_traveler: 'Fellow traveler',
  account_style_matches_comments: 'Style match',
  comments_match_cluster: 'Content match',
};

export function InsightsRail({ crossLinks }: { crossLinks: CrossLink[] }) {
  const sorted = [...crossLinks].sort((a, b) => {
    const rank = { high: 4, elevated: 3, moderate: 2, info: 1 } as const;
    return (rank[b.severity] || 0) - (rank[a.severity] || 0);
  });
  return (
    <div className="p-4 space-y-5 h-full overflow-y-auto">
      <header className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase flex items-center gap-1.5">
        <Link2 size={11} /> Cross-links · {crossLinks.length}
      </header>
      {sorted.length === 0 ? (
        <div className="text-xs text-fg-mute leading-relaxed">
          No cross-connections detected between your inputs. Each input was
          scanned independently.
        </div>
      ) : (
        <div className="space-y-3">
          {sorted.map((l, i) => (
            <article
              key={i}
              className={`p-3 border rounded-sm ${SEV_STYLE[l.severity]}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono text-2xs tracking-wider uppercase">
                  {KIND_LABEL[l.kind] || l.kind.replace(/_/g, ' ')}
                </span>
                <span className="font-mono text-2xs tracking-wider uppercase opacity-80">
                  {l.severity}
                </span>
              </div>
              <p className="text-xs text-fg leading-relaxed mb-2">{l.summary}</p>
              {l.evidence.slice(0, 2).map((e, j) => (
                <p key={j} className="text-2xs text-fg-dim font-mono leading-relaxed">
                  ↳ {e}
                </p>
              ))}
              {l.related_entities.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {l.related_entities.slice(0, 4).map((e) => (
                    <span
                      key={e}
                      className="px-1.5 py-0.5 font-mono text-2xs border border-current/40 rounded-sm"
                    >
                      {e.slice(0, 12)}{e.length > 12 ? '…' : ''}
                    </span>
                  ))}
                  {l.related_entities.length > 4 && (
                    <span className="font-mono text-2xs text-fg-mute">
                      +{l.related_entities.length - 4}
                    </span>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
