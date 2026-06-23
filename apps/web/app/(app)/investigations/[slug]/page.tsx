import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { ApiError, type InvestigationDetailResponse, VERDICT_LABELS } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { Card, CardLabel } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { SavedInvestigationViewer } from './viewer';
import { ShareBlock } from './share-block';
import { CommentaryBlock } from './commentary-block';
import { VerdictWidget } from './verdict-widget';
import { env } from '@/lib/env';

export const dynamic = 'force-dynamic';

export async function generateMetadata({ params }: { params: { slug: string } }) {
  return { title: `Investigation ${params.slug} — OMISPHERE` };
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

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg transition-colors font-mono tracking-wider uppercase"
        >
          <ArrowLeft size={14} /> Back to dashboard
        </Link>
      </div>

      {/* Hero header */}
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev p-6 md:p-8">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="relative flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            <span className="section-label">Saved investigation · {inv.slug}</span>
            <h1 className="display text-2xl md:text-3xl font-semibold text-fg tracking-tight mb-2 mt-3">{inv.label}</h1>
            <p className="font-mono text-xs text-fg-faint break-all">{inv.input_url}</p>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            {inv.verdict && inv.verdict !== 'pending' && (
              <span className="font-mono text-2xs tracking-wider uppercase text-fg-mute border border-border-hot px-2.5 py-1 rounded-full bg-bg-elev-2">
                {VERDICT_LABELS[inv.verdict]}
              </span>
            )}
            <TierBadge tier={inv.overall_tier} size="lg" />
          </div>
        </div>

        {/* Inline metadata strip */}
        <div className="relative mt-6 pt-5 border-t border-border-1/60 grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-sm">
          <Row label="Probability" value={`${Math.round(inv.overall_probability * 100)}%`} />
          <Row label="Batches"     value={String(inv.batch_count)} />
          <Row label="YT quota"    value={`${inv.quota_used} units`} />
          <Row label="Created"     value={new Date(inv.created_at).toLocaleString()} />
        </div>

        {/* E2 — reproducibility note. Scores can legitimately move between runs
            as cross-scan memory accumulates; frame it as evidence sharpening,
            not unreliability, and point at the indicators that show what changed. */}
        <p className="relative mt-4 text-2xs leading-relaxed text-fg-faint border-t border-border-1/60 pt-4">
          Scores can shift if you re-run this investigation: Omi&apos;s cross-scan
          memory accumulates evidence over time, so a network that keeps acting
          together scores more confidently on a later pass. The per-account{' '}
          <span className="text-fg-mute">cached</span> and{' '}
          <span className="text-fg-mute">prior neighbors</span> indicators show
          which inputs changed — this is evidence evolving, not a different answer
          to the same question.
        </p>
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

      <CommentaryBlock
        slug={inv.slug}
        initialText={inv.commentary_text}
        initialProvider={inv.commentary_provider}
        initialGeneratedAt={inv.commentary_generated_at}
      />

      <ShareBlock
        slug={inv.slug}
        initialToken={inv.share_token}
        publicBaseUrl={env.PUBLIC_BASE_URL}
      />

      <SavedInvestigationViewer payload={inv.payload} />
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
