import { notFound } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  User,
  MessageCircle,
  Layers,
  Calendar,
  Shield,
  ShieldAlert,
  AlertTriangle,
  Flame,
  ArrowRight,
} from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import {
  type AuthorPresenceResponse,
  type AuthorContentRow,
  ApiError,
} from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';

export const dynamic = 'force-dynamic';

export async function generateMetadata({
  params,
}: {
  params: { platform: string; id: string };
}) {
  return { title: `Author ${params.id} — OMISPHERE` };
}

const RISK_CONFIG: Record<string, { label: string; icon: React.ReactNode; cls: string }> = {
  extreme: { label: 'Extreme', icon: <Flame size={10} />, cls: 'text-tier-high border-tier-high/40 bg-tier-high/10' },
  high: { label: 'High', icon: <ShieldAlert size={10} />, cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  elevated: { label: 'High', icon: <ShieldAlert size={10} />, cls: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10' },
  moderate: { label: 'Moderate', icon: <AlertTriangle size={10} />, cls: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10' },
  low: { label: 'Low', icon: <Shield size={10} />, cls: 'text-tier-low border-tier-low/40 bg-tier-low/10' },
};

export default async function AuthorPresencePage({
  params,
}: {
  params: { platform: string; id: string };
}) {
  let data: AuthorPresenceResponse;
  try {
    data = await apiServer<AuthorPresenceResponse>(
      `/v1/content/authors/${params.platform}/${encodeURIComponent(params.id)}`,
    );
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) notFound();
    return (
      <Card>
        <CardLabel>Error loading author</CardLabel>
        <CardTitle>Something went wrong</CardTitle>
        <p className="text-sm text-fg-dim">
          {err instanceof ApiError ? err.message : 'Unknown error'}
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Link
        href="/content"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg transition-colors"
      >
        <ArrowLeft size={12} /> Content database
      </Link>

      {/* Header */}
      <header className="bg-bg-elev border border-border-1 rounded-md p-5">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-10 h-10 rounded-full bg-bg border border-border-1 flex items-center justify-center text-fg-mute">
            <User size={18} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
              {data.platform} · author footprint
            </p>
            <h1 className="text-xl font-semibold text-fg tracking-tight truncate">
              {data.author_handle || data.author_external_id}
            </h1>
            {data.author_handle && (
              <p className="font-mono text-2xs text-fg-faint truncate">
                {data.author_external_id}
              </p>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
          <Stat label="Content seen on" value={data.content_count} icon={<Layers size={11} />} />
          <Stat label="Total comments" value={data.total_comments} icon={<MessageCircle size={11} />} />
          <Stat label="First seen" value={data.first_seen ? timeAgo(data.first_seen) : '—'} icon={<Calendar size={11} />} />
          <Stat label="Last seen" value={data.last_seen ? timeAgo(data.last_seen) : '—'} icon={<Calendar size={11} />} />
        </div>
      </header>

      <div>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-3">
          Content this author has commented on
        </p>
        <div className="space-y-2">
          {data.entities.map((row) => (
            <AuthorContentCard key={row.entity.id} row={row} />
          ))}
        </div>
      </div>
    </div>
  );
}

function AuthorContentCard({ row }: { row: AuthorContentRow }) {
  const e = row.entity;
  const risk = RISK_CONFIG[e.latest_risk_tier] ?? RISK_CONFIG.low;
  return (
    <Link
      href={`/content/${e.platform}/${e.content_id}`}
      className="block group"
    >
      <article className="bg-bg-elev border border-border-1 rounded-md p-4 hover:border-border-hot group-hover:bg-bg-elev-2/30 transition-colors">
        <div className="flex items-start gap-3">
          {e.thumbnail_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={e.thumbnail_url}
              alt=""
              className="w-20 h-12 object-cover rounded-sm shrink-0 border border-border-1"
            />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <span className="font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-mute">
                {e.platform}
              </span>
              <span
                className={`inline-flex items-center gap-1 font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border ${risk.cls}`}
              >
                {risk.icon}
                {risk.label}
              </span>
              <span className="font-mono text-2xs text-accent">
                {row.comment_count} comment{row.comment_count !== 1 ? 's' : ''}
              </span>
            </div>
            <p className="text-sm text-fg font-medium leading-tight line-clamp-1">
              {e.title || e.content_id}
            </p>
            <p className="text-2xs text-fg-dim mt-1 line-clamp-2 italic">
              &ldquo;{row.sample_text}&rdquo;
            </p>
            <div className="flex items-center gap-3 mt-1.5 font-mono text-2xs text-fg-mute">
              <span>First: {timeAgo(row.first_comment)}</span>
              <span>Latest: {timeAgo(row.last_comment)}</span>
            </div>
          </div>
          <ArrowRight size={14} className="text-fg-faint group-hover:text-accent transition-colors shrink-0 mt-1" />
        </div>
      </article>
    </Link>
  );
}

function Stat({ label, value, icon }: { label: string; value: string | number; icon?: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-0.5">
        {icon}
        {label}
      </div>
      <div className="font-mono text-base font-medium tabular-nums text-fg">{value}</div>
    </div>
  );
}
