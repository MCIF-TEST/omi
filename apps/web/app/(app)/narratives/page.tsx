import { MessageSquareText, Users, TrendingUp, Clock } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { type NarrativesResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const metadata = { title: 'Narratives — OMISPHERE' };
export const dynamic = 'force-dynamic';

export default async function NarrativesPage({
  searchParams,
}: {
  searchParams: { window?: string };
}) {
  const window_days = Math.max(1, Math.min(90, parseInt(searchParams.window || '7', 10) || 7));
  let data: NarrativesResponse;
  try {
    data = await apiServer<NarrativesResponse>(`/v1/narratives?window_days=${window_days}&limit=30`);
  } catch (e) {
    data = { window_days, embedder: 'unknown', narratives: [] };
  }

  return (
    <div className="space-y-8">
      <header className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Narrative observatory
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">
            Narratives spreading across OMISPHERE
          </h1>
          <p className="mt-2 text-sm text-fg-dim max-w-2xl">
            Semantic clusters of comments — same topic, same framing — across all
            scanned accounts and videos. Trending = volume × spread (more distinct
            authors saying the same thing is more interesting than one account
            repeating itself).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Window
          </span>
          {[1, 7, 30, 90].map((d) => (
            <a
              key={d}
              href={`/narratives?window=${d}`}
              className={`font-mono text-2xs tracking-wider uppercase px-2 py-1 rounded-sm border ${
                d === window_days
                  ? 'border-accent-dim bg-accent/10 text-accent'
                  : 'border-border-2 text-fg-dim hover:text-fg'
              }`}
            >
              {d}d
            </a>
          ))}
        </div>
      </header>

      <div className="flex items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
        <span>Embedder · <span className="text-accent">{data.embedder}</span></span>
        <span>·</span>
        <span>{data.narratives.length} narratives</span>
      </div>

      {data.narratives.length === 0 ? (
        <Card>
          <CardLabel>No narratives in this window</CardLabel>
          <CardTitle>The observatory is empty</CardTitle>
          <p className="text-sm text-fg-dim">
            Narratives are built from scanned comments. Run more scans to populate
            the observatory — every comment longer than ~18 characters gets
            clustered into the cross-corpus narrative store.
          </p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.narratives.map((n) => (
            <article
              key={n.id}
              className="bg-bg-elev border border-border-1 rounded-md p-5 hover:border-border-hot transition-colors"
            >
              <div className="flex items-center justify-between mb-3 gap-2">
                <Badge variant="accent">
                  <MessageSquareText size={11} /> Narrative #{n.id}
                </Badge>
                <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
                  {timeAgo(n.last_seen_at)}
                </span>
              </div>
              <p className="text-sm text-fg leading-relaxed mb-4 line-clamp-3">
                &ldquo;{n.sample_text || '(no sample)'}&rdquo;
              </p>
              <div className="grid grid-cols-3 gap-3 text-2xs font-mono uppercase tracking-wider text-fg-mute">
                <Stat
                  icon={<TrendingUp size={11} />}
                  label="Recent"
                  value={String(n.recent_members)}
                />
                <Stat
                  icon={<Users size={11} />}
                  label="Authors"
                  value={String(n.distinct_authors)}
                />
                <Stat
                  icon={<Clock size={11} />}
                  label="Total"
                  value={String(n.member_count)}
                />
              </div>
              <div className="mt-3 h-1 bg-border-1 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${Math.min(100, n.spread_ratio * 100)}%` }}
                  aria-label={`spread ratio ${Math.round(n.spread_ratio * 100)}%`}
                />
              </div>
              <div className="mt-1 font-mono text-2xs text-fg-mute">
                {Math.round(n.spread_ratio * 100)}% spread
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div>
      <div className="flex items-center gap-1 mb-0.5">{icon}<span>{label}</span></div>
      <div className="text-fg mono text-sm">{value}</div>
    </div>
  );
}
