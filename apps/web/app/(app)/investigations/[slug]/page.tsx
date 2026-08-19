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
          className="inline-flex items-center gap-1.5 meta meta-hi hover:text-fg transition-colors"
        >
          <ArrowLeft size={14} /> Back to investigations
        </Link>
      </div>

      {/* Case header. Ticked, because this is the record everything else on the
          page is about and the ticks are rationed to exactly that. */}
      <header className="relative overflow-hidden rounded-xl border border-border-1 bg-bg-elev tick-frame p-6 md:p-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        {/* Stacks on phones. As a single row it put a ~250px shrink-0 action cluster beside a
            `flex-1 min-w-0` text column, so on a narrow screen the text column collapsed to almost
            nothing: the title rendered two characters per line ("Ba" / "I…") and the URL as "htt…",
            while the non-wrapping section label spilled out of its own box and printed underneath
            the button. The title needs the full width; the actions belong under it. */}
        <div className="relative flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 sm:flex-1">
            {/* The slug is the case reference, so it is presented as one:
                labelled, in the data voice, selectable. It used to be tacked
                onto the end of an eyebrow sentence where it read as noise. */}
            <div className="flex items-center gap-2.5 min-w-0">
              <span className="meta shrink-0">Case</span>
              <span className="h-px w-4 bg-border-hot shrink-0" aria-hidden />
              <span className="meta meta-on truncate select-all">{inv.slug}</span>
            </div>
            <h1 className="display-hard-sm text-xl sm:text-2xl md:text-[1.9rem] text-fg mb-1.5 mt-3 line-clamp-2 break-words">{inv.label}</h1>
            <p className="font-mono text-xs text-fg-faint truncate">{inv.input_url}</p>
          </div>
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap sm:shrink-0">
            {inv.verdict && inv.verdict !== 'pending' && (
              // A square plate with a lamp, not a rounded chip. This carries the
              // analyst's own conclusion about a case; the pill shape put it in
              // the same visual class as a decorative tag.
              <span className="inline-flex items-center gap-2 meta meta-on border border-border-hot px-2.5 h-8 rounded-sm bg-bg-elev-2">
                <span className="led led-off" />
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
        <hr className="rule-rack relative mt-6" />
        <div className="relative pt-4 grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-3">
          {/* "Batches" alone was ambiguous on a page whose other panel also
              counts batches: this is how many passes the SCAN ran, not how many
              the analyst did. */}
          <Row label="Scan batches" value={String(inv.batch_count)} />
          <Row label="YT quota"     value={`${inv.quota_used} units`} />
          <Row label="Created"      value={new Date(inv.created_at).toLocaleString()} />
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
      <AnalystPanel slug={inv.slug} scanned={scanned} createdAt={inv.created_at}
                    platform={inv.platform} />

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
    <div className="readout">
      <dt className="meta">{label}</dt>
      <dd className="readout-v text-[0.8125rem]">{value}</dd>
    </div>
  );
}
