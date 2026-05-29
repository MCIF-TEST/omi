import { AlertTriangle, Info, AlertCircle, Flame } from 'lucide-react';
import { type CrossLink } from '@/lib/api';

const SEV_STYLE: Record<CrossLink['severity'], { card: string; icon: React.ReactNode }> = {
  high:     { card: 'border-tier-high/40    bg-tier-high/[0.07]',     icon: <Flame       size={12} className="text-tier-high"     /> },
  elevated: { card: 'border-tier-elevated/40 bg-tier-elevated/[0.07]', icon: <AlertCircle size={12} className="text-tier-elevated" /> },
  moderate: { card: 'border-tier-moderate/40 bg-tier-moderate/[0.07]', icon: <AlertTriangle size={12} className="text-tier-moderate" /> },
  info:     { card: 'border-accent/30        bg-accent/[0.06]',        icon: <Info        size={12} className="text-accent"         /> },
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
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-12 text-center">
          <div className="w-10 h-10 rounded-xl bg-bg-elev-2 border border-border-2 flex items-center justify-center text-fg-faint">
            <Info size={16} />
          </div>
          <p className="text-xs text-fg-mute leading-relaxed max-w-[22ch]">
            No cross-connections detected. Each input was scanned independently.
          </p>
        </div>
      ) : (
        sorted.map((l, i) => {
          const { card, icon } = SEV_STYLE[l.severity] || SEV_STYLE.info;
          return (
            <article key={i} className={`p-3.5 border rounded-xl ${card}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5">
                  {icon}
                  <span className="font-mono text-2xs tracking-wider uppercase text-fg">
                    {KIND_LABEL[l.kind] || l.kind.replace(/_/g, ' ')}
                  </span>
                </div>
                <span className={`font-mono text-2xs tracking-wider uppercase px-2 py-0.5 rounded-full border ${card}`}>
                  {l.severity}
                </span>
              </div>
              <p className="text-xs text-fg leading-relaxed mb-2.5">{l.summary}</p>
              {l.evidence.slice(0, 2).map((e, j) => (
                <p key={j} className="text-2xs text-fg-dim font-mono leading-relaxed mb-0.5">
                  ↳ {e}
                </p>
              ))}
              {l.related_entities.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1">
                  {l.related_entities.slice(0, 4).map((e) => (
                    <span key={e} className="px-1.5 py-0.5 font-mono text-2xs border border-current/30 rounded-full text-fg-dim">
                      {e.slice(0, 12)}{e.length > 12 ? '…' : ''}
                    </span>
                  ))}
                  {l.related_entities.length > 4 && (
                    <span className="font-mono text-2xs text-fg-mute">+{l.related_entities.length - 4}</span>
                  )}
                </div>
              )}
            </article>
          );
        })
      )}
    </div>
  );
}
