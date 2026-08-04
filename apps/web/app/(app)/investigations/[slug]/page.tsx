import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Radar } from 'lucide-react';
import { ApiError, type InvestigationDetailResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { Card, CardLabel } from '@/components/ui/card';
import { ShareBlock } from './share-block';
import { AnalystPanel } from './analyst-panel';
import { VerdictWidget } from './verdict-widget';
import { scannedAccountsFrom } from '@/lib/investigation-export';
import { env } from '@/lib/env';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { slug: string } }) {
  return { title: `Investigation ${params.slug}. OMISPHERE` };
}

export default async function InvestigationPage({ params }: { params: { slug: string } }) {
  let inv: InvestigationDetailResponse;
  try {
    inv = await apiServer<InvestigationDetailResponse>(
      `/v1/investigations/${encodeURIComponent(params.slug)}`,
    );
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  // Projected HERE, on the server. `inv.payload` is the whole stored scan (every account's evidence,
  // posts and analyst sections, megabytes on a large investigation) and the page renders none of it.
  // Handing it to a client component to build a table would serialise all of it into the HTML for a
  // button most visits never press; this is a few hundred bytes per account.
  const scanned = scannedAccountsFrom(inv.payload);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/investigations"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg transition-colors font-mono tracking-wider uppercase"
        >
          <ArrowLeft size={14} /> Back to investigations
        </Link>
      </div>

      {/* Hero header */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev p-6 md:p-8">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        {/* Stacks on phones. As a single row it put a ~250px shrink-0 action cluster beside a
            `flex-1 min-w-0` text column, so on a narrow screen the text column collapsed to almost
            nothing: the title rendered two characters per line ("Ba" / "I…") and the URL as "htt…",
            while the non-wrapping section label spilled out of its own box and printed underneath
            the button. The title needs the full width; the actions belong under it. */}
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 sm:flex-1">
            <span className="section-label">Saved investigation · {inv.slug}</span>
            <h1 className="display text-xl sm:text-2xl md:text-3xl font-semibold text-fg tracking-tight mb-1.5 mt-3 line-clamp-2 break-words">{inv.label}</h1>
            <p className="font-mono text-xs text-fg-faint truncate">{inv.input_url}</p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap sm:shrink-0">
            {inv.verdict && inv.verdict !== 'pending' && (
              <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute border border-border-hot px-2.5 py-1 rounded-full bg-bg-elev-2">
                {VERDICT_LABELS[inv.verdict]}
              </span>
            )}
            {inv.input_url && (
              <Link
                href={`/investigate?url=${encodeURIComponent(inv.input_url)}`}
                className="btn-slab h-9 px-4 rounded-md text-xs font-medium inline-flex items-center gap-1.5 text-fg-dim"
              >
                <Radar size={13} className="text-accent" />
                Scan more commenters
              </Link>
            )}
          </div>
        </div>

        {/* Inline metadata strip. Run identity only. The suspicion read now lives
            in the Omi Analyst assessment below (the deterministic engine still runs
            underneath to supply the evidence the model reasons over). */}
        <div className="relative mt-6 pt-5 border-t border-border-1/60 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3 text-sm">
          <Row label="Batches"     value={String(inv.batch_count)} />
          <Row label="YT quota"    value={`${inv.quota_used} units`} />
          <Row label="Created"     value={new Date(inv.created_at).toLocaleString()} />
        </div>
      </header>

      {/* Analyst verdict + notes */}
      <Card>
        <CardLabel>Analyst verdict</CardLabel>
        <p className="text-xs text-fg-mute mb-4">
          Mark this investigation once you&apos;ve reached a conclusion. Visible only to you.
        </p>
        <VerdictWidget
          slug={inv.slug}
          initialVerdict={inv.verdict}
          initialNotes={inv.notes}
        />
      </Card>

      {/* Single governed AI surface: the Omi Analyst assessment is generated from the one
          model-backed inference per investigation. The former free-text commentary block
          (separate Anthropic/template path) is retired to keep one report from one inference. */}
      <AnalystPanel slug={inv.slug} scanned={scanned} createdAt={inv.created_at} />

      <ShareBlock
        slug={inv.slug}
        initialToken={inv.share_token}
        publicBaseUrl={env.PUBLIC_BASE_URL}
      />
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <dt className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-0.5">{label}</dt>
      <dd className="text-fg mono">{value}</dd>
    </div>
  );
}
