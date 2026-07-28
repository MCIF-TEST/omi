import Link from 'next/link';
import {
  Search, ArrowRight, CheckCircle2, FolderSearch, Sparkles,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { InvestigationThumb } from '@/components/shared/investigation-thumb';
import { type InvestigationSummary, type InvestigationsListResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/cn';

export const metadata = { title: 'Previous investigations. OMISPHERE' };
export const dynamic = 'force-dynamic';

const CHIP = 'font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-full border transition-colors';
const CHIP_ON = 'border-transparent bg-accent/15 text-accent shadow-[inset_0_0_0_1px_rgba(217,164,74,0.4)]';
const CHIP_OFF = 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot';

const PLATFORM_FILTERS = [
  { value: '', label: 'All' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'x', label: 'X' },
] as const;

export default async function InvestigationsPage({
  searchParams,
}: {
  searchParams: { platform?: string; q?: string };
}) {
  const platformFilter = (searchParams.platform || '').toLowerCase();
  const query = (searchParams.q || '').trim().toLowerCase();

  const data = await apiServer<InvestigationsListResponse>(
    '/v1/investigations?limit=100',
  ).catch(() => ({ investigations: [] } as InvestigationsListResponse));

  let investigations = data.investigations ?? [];

  if (platformFilter === 'youtube' || platformFilter === 'x') {
    investigations = investigations.filter((i) => normalizePlatform(i) === platformFilter);
  }
  if (query) {
    investigations = investigations.filter((i) => {
      const hay = `${i.label} ${i.summary} ${i.input_url} ${i.target_id || ''}`.toLowerCase();
      return hay.includes(query);
    });
  }

  const open = investigations.filter((i) => !i.verdict || i.verdict === 'pending');
  const concluded = investigations.filter((i) => i.verdict && i.verdict !== 'pending');
  const ytCount = (data.investigations ?? []).filter((i) => normalizePlatform(i) === 'youtube').length;
  const xCount = (data.investigations ?? []).filter((i) => normalizePlatform(i) === 'x').length;

  return (
    <div className="space-y-6 animate-fade-up">
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <span
          className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-violet/15 blur-3xl"
          aria-hidden
        />
        <span
          className="pointer-events-none absolute -left-8 bottom-0 h-28 w-28 rounded-full bg-accent/10 blur-2xl"
          aria-hidden
        />
        <div className="relative flex items-end justify-between gap-4 flex-wrap">
          <div className="min-w-0">
            <span className="section-label inline-flex items-center gap-1.5">
              <Sparkles size={11} className="text-accent" />
              Intelligence · Archive
            </span>
            <h1 className="display text-2xl md:text-3xl font-semibold text-fg tracking-tight mt-3">
              Previous investigations
            </h1>
            <p className="text-sm text-fg-dim mt-1.5 max-w-xl leading-relaxed">
              Your personal archive of every scan. YouTube videos and X posts with
              thumbnails, verdicts, and evidence in one place.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
              <span className="text-fg-dim tabular">
                {investigations.length} shown
                {(platformFilter || query) && data.investigations?.length
                  ? ` of ${data.investigations.length}`
                  : ''}
              </span>
              {ytCount > 0 && (
                <>
                  <span className="text-border-2">·</span>
                  <span>{ytCount} YouTube</span>
                </>
              )}
              {xCount > 0 && (
                <>
                  <span className="text-border-2">·</span>
                  <span>{xCount} X</span>
                </>
              )}
              {concluded.length > 0 && (
                <>
                  <span className="text-border-2">·</span>
                  <span>{concluded.length} concluded</span>
                </>
              )}
            </div>
          </div>
          <div className="flex gap-2.5 shrink-0">
            <Link href="/bulk"><Button variant="secondary">Bulk scan</Button></Link>
            <Link href="/investigate">
              <Button size="lg" className="btn-glow">
                <Search size={15} /> New investigation
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <form action="/investigations" method="GET" className="flex items-center gap-2 flex-1">
          {platformFilter && <input type="hidden" name="platform" value={platformFilter} />}
          <div className="relative flex-1 max-w-md">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
            <input
              aria-label="Search previous investigations"
              type="search"
              name="q"
              defaultValue={searchParams.q || ''}
              placeholder="Search titles, URLs, IDs…"
              className="w-full pl-9 pr-3 h-10 bg-bg-elev-2 border border-border-2 rounded-md text-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/25 transition-colors"
              autoComplete="off"
            />
          </div>
          {query && (
            <Link
              href={platformFilter ? `/investigations?platform=${platformFilter}` : '/investigations'}
              className={`${CHIP} ${CHIP_OFF}`}
            >
              Clear
            </Link>
          )}
        </form>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">Platform</span>
          {PLATFORM_FILTERS.map((f) => (
            <Link
              key={f.value || 'all'}
              href={buildHref({ platform: f.value, q: searchParams.q || '' })}
              className={`${CHIP} ${f.value === platformFilter ? CHIP_ON : CHIP_OFF}`}
            >
              {f.label}
            </Link>
          ))}
        </div>
      </div>

      {(data.investigations ?? []).length === 0 ? (
        <Card className="text-center py-14">
          <div className="w-14 h-14 mx-auto mb-4 rounded-2xl border border-border-2 bg-gradient-to-br from-accent/15 to-violet/10 flex items-center justify-center text-accent">
            <FolderSearch size={22} strokeWidth={1.5} />
          </div>
          <h3 className="display text-base font-semibold text-fg mb-1.5">Your archive is empty</h3>
          <p className="text-sm text-fg-dim mb-6 max-w-md mx-auto leading-relaxed">
            Paste a YouTube video or X account, run a scan, and it lands here with a
            thumbnail, risk tier, and shareable evidence trail.
          </p>
          <Link href="/investigate">
            <Button className="btn-glow"><Search size={14} /> Run your first scan</Button>
          </Link>
        </Card>
      ) : investigations.length === 0 ? (
        <Card className="text-center py-12">
          <h3 className="display text-base font-semibold text-fg mb-1.5">No matches</h3>
          <p className="text-sm text-fg-dim mb-4">
            Nothing matched that filter. Try another platform or clear the search.
          </p>
          <Link href="/investigations">
            <Button variant="secondary">Show all</Button>
          </Link>
        </Card>
      ) : (
        <div className="space-y-8">
          {open.length > 0 && (
            <section>
              <SectionHead
                tone="open"
                label="Open"
                count={open.length}
                hint="Still in play. Pick up where you left off"
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5">
                {open.map((inv) => (
                  <InvestigationCard key={inv.slug} inv={inv} />
                ))}
              </div>
            </section>
          )}
          {concluded.length > 0 && (
            <section>
              <SectionHead
                tone="done"
                label="Concluded"
                count={concluded.length}
                hint="Verdict locked in"
              />
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3.5">
                {concluded.map((inv) => (
                  <InvestigationCard key={inv.slug} inv={inv} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function SectionHead({
  tone,
  label,
  count,
  hint,
}: {
  tone: 'open' | 'done';
  label: string;
  count: number;
  hint: string;
}) {
  return (
    <div className="flex items-center gap-2.5 mb-3 px-0.5">
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full',
          tone === 'open' ? 'bg-tier-moderate' : 'bg-tier-low',
        )}
      />
      <h2 className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
        {label} · {count}
      </h2>
      <span className="text-border-2">·</span>
      <span className="text-xs text-fg-faint hidden sm:inline">{hint}</span>
    </div>
  );
}

function InvestigationCard({ inv }: { inv: InvestigationSummary }) {
  const platform = normalizePlatform(inv);
  const thumb = resolveThumbnail(inv, platform);
  const pct = Math.round(inv.overall_probability * 100);
  const concluded = inv.verdict && inv.verdict !== 'pending';

  return (
    <Link
      href={`/investigations/${inv.slug}`}
      className="group block h-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 rounded-xl"
    >
      <article className="h-full flex flex-col bg-bg-elev border border-border-1 rounded-xl overflow-hidden card-interactive transition-all duration-300 group-hover:border-border-hot group-hover:shadow-card-lg">
        <InvestigationThumb
          platform={platform}
          thumbnailUrl={thumb}
          label={inv.label}
          size="md"
        />

        <div className="flex flex-col flex-1 p-4 gap-3">
          <div className="min-w-0">
            <div className="flex items-start gap-2 mb-1.5 flex-wrap">
              <TierBadge tier={inv.overall_tier} size="sm" />
              {inv.confidence != null && inv.confidence < 0.4 && (
                <span
                  title={`Low confidence (${Math.round(inv.confidence * 100)}%). Limited data backed this verdict.`}
                  className="font-mono text-[0.55rem] tracking-wider uppercase text-confidence-weak border border-border-2 rounded-full px-1.5 py-px"
                >
                  low conf
                </span>
              )}
              {concluded && (
                <span className="inline-flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider">
                  <CheckCircle2 size={10} className="text-tier-low" />
                  {VERDICT_LABELS[inv.verdict!] ?? inv.verdict}
                </span>
              )}
            </div>
            <h3 className="text-sm font-medium text-fg leading-snug line-clamp-2 group-hover:text-accent-text transition-colors">
              {inv.label}
            </h3>
            {inv.summary && (
              <p className="mt-1 text-xs text-fg-dim line-clamp-2 leading-relaxed">{inv.summary}</p>
            )}
          </div>

          {/* Probability bar */}
          <div className="mt-auto">
            <div className="flex items-center justify-between font-mono text-2xs mb-1.5">
              <span className="text-fg-mute uppercase tracking-wider">Suspicion</span>
              <span className="text-fg tabular">{pct}%</span>
            </div>
            <div className="h-1 bg-bg-elev-3 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-brand-gradient transition-all"
                style={{ width: `${Math.min(100, Math.max(2, pct))}%` }}
              />
            </div>
          </div>

          <div className="flex items-center justify-between pt-0.5 font-mono text-2xs text-fg-mute uppercase tracking-wider">
            <span className="truncate">
              {timeAgo(inv.created_at)}
              <span className="text-border-2 mx-1.5">·</span>
              {inv.batch_count} batch{inv.batch_count === 1 ? '' : 'es'}
            </span>
            <ArrowRight
              size={13}
              className="text-fg-faint group-hover:text-accent group-hover:translate-x-0.5 transition-all shrink-0"
            />
          </div>
        </div>
      </article>
    </Link>
  );
}

function normalizePlatform(inv: InvestigationSummary): string {
  const p = (inv.platform || '').toLowerCase();
  if (p === 'x' || p === 'twitter') return 'x';
  if (p === 'youtube') return 'youtube';
  const url = (inv.input_url || '').toLowerCase();
  if (url.includes('youtube.com') || url.includes('youtu.be')) return 'youtube';
  if (url.includes('twitter.com') || url.includes('x.com')) return 'x';
  return 'unknown';
}

/** Prefer API thumb; fall back to deriving YouTube hqdefault from target/url. */
function resolveThumbnail(inv: InvestigationSummary, platform: string): string | null {
  if (inv.thumbnail_url) return inv.thumbnail_url;
  if (platform !== 'youtube') return null;
  const vid = youtubeIdFrom(inv);
  return vid ? `https://i.ytimg.com/vi/${vid}/hqdefault.jpg` : null;
}

function youtubeIdFrom(inv: InvestigationSummary): string | null {
  const bare = /^[A-Za-z0-9_-]{11}$/;
  if (inv.target_id && bare.test(inv.target_id)) return inv.target_id;
  const url = inv.input_url || '';
  const m = url.match(
    /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/|live\/|v\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/i,
  );
  if (m) return m[1];
  try {
    const u = new URL(url);
    const v = u.searchParams.get('v');
    if (v && bare.test(v)) return v;
  } catch {
    /* ignore */
  }
  return null;
}

function buildHref({ platform, q }: { platform: string; q: string }) {
  const params = new URLSearchParams();
  if (platform) params.set('platform', platform);
  if (q) params.set('q', q);
  const qs = params.toString();
  return qs ? `/investigations?${qs}` : '/investigations';
}

