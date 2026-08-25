import Link from 'next/link';
import {
  Search, ArrowRight, CheckCircle2, FolderSearch,
} from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { TierBadge } from '@/components/shared/tier-badge';
import { InvestigationThumb } from '@/components/shared/investigation-thumb';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { type InvestigationSummary, type InvestigationsListResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { timeAgo } from '@/lib/format';
import { cn } from '@/lib/cn';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

export const metadata = { title: 'Previous investigations' };
export const dynamic = 'force-dynamic';

const CHIP = 'font-mono text-2xs tracking-wider uppercase px-2.5 py-1.5 rounded-sm border transition-colors';
const CHIP_ON = 'border-accent/70 bg-accent/15 text-accent-text';
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
      <ConsoleHeader
        index={SECTION_INDEX['/investigations']}
        eyebrow="Intelligence · Archive"
        title="Previous investigations"
        lede="Your personal archive of every scan. YouTube videos and X posts with thumbnails, verdicts, and evidence in one place."
        readout={
          // The archive's own census, as labelled readouts rather than a row of
          // interpuncted words. These are counts, and a count belongs under a
          // label in the data voice.
          <div className="flex items-stretch border border-border-1 rounded-sm bg-bg divide-x divide-border-1">
            <span className="readout px-3 py-1.5">
              <span className="meta">Shown</span>
              <span className="readout-v text-[0.8125rem]">
                {investigations.length}
                {(platformFilter || query) && data.investigations?.length
                  ? <span className="text-fg-faint"> / {data.investigations.length}</span>
                  : ''}
              </span>
            </span>
            {ytCount > 0 && (
              <span className="readout px-3 py-1.5">
                <span className="meta">YouTube</span>
                <span className="readout-v text-[0.8125rem]">{ytCount}</span>
              </span>
            )}
            {xCount > 0 && (
              <span className="readout px-3 py-1.5">
                <span className="meta">X</span>
                <span className="readout-v text-[0.8125rem]">{xCount}</span>
              </span>
            )}
            {concluded.length > 0 && (
              <span className="readout px-3 py-1.5">
                <span className="meta">Concluded</span>
                <span className="readout-v text-[0.8125rem]">{concluded.length}</span>
              </span>
            )}
          </div>
        }
      >
        <div className="relative flex items-end justify-end gap-4 flex-wrap">
          <div className="flex gap-2.5 shrink-0">
            <Link href="/bulk"><Button variant="secondary">Bulk scan</Button></Link>
            <Link href="/investigate">
              <Button size="lg" className="btn-glow">
                <Search size={15} /> New investigation
              </Button>
            </Link>
          </div>
        </div>
      </ConsoleHeader>

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
              className="w-full pl-9 pr-3 h-10 bg-bg-inset border border-border-2 rounded-sm text-sm text-fg placeholder:text-fg-mute focus:border-accent focus-hard transition-colors"
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
          {/* Flat tint. This was a blue-to-purple diagonal, which the design
              language forbids by name: blue is the identity and purple is the
              AI layer, so a gradient between them says neither. */}
          <div className="w-14 h-14 mx-auto mb-4 rounded-xl border border-border-2 bg-accent/10 flex items-center justify-center text-accent">
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
      className="group block h-full focus-hard focus-visible:outline-none rounded-xl"
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
                  className="font-mono text-[0.55rem] tracking-wider uppercase text-confidence-weak border border-border-2 rounded-sm px-1.5 py-px"
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

          {/* Suspicion meter. The shared graduated bar, filled flat in this
              record's OWN tier colour.
              It used to be a `bg-brand-gradient` fill, which is the whole
              suspicion ramp (green through red) painted along the length of one
              bar: a card at 43% showed green fading to amber and a card at 90%
              showed green through red, so the colour under the number described
              the distance travelled rather than the reading. One value, one
              colour, against marked boundaries. */}
          <div className="mt-auto">
            <div className="flex items-center justify-between mb-1.5">
              <span className="meta meta-hi">Suspicion</span>
              <span className="font-mono text-2xs text-fg tabular">{pct}%</span>
            </div>
            <ProbabilityBar
              value={inv.overall_probability}
              tier={inv.overall_tier}
              size="sm"
              showLabel={false}
            />
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

