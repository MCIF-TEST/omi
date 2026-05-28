import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { ApiError, type InvestigationDetailResponse } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { Card, CardLabel } from '@/components/ui/card';
import { TierBadge } from '@/components/shared/tier-badge';
import { SavedInvestigationViewer } from './viewer';
import { ShareBlock } from './share-block';
import { CommentaryBlock } from './commentary-block';
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
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg-dim font-mono tracking-wider uppercase"
        >
          <ArrowLeft size={14} /> Back to dashboard
        </Link>
      </div>

      <header className="flex items-baseline justify-between gap-4 flex-wrap">
        <div>
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
            Saved investigation · {inv.slug}
          </p>
          <h1 className="text-2xl font-semibold text-fg tracking-tight">{inv.label}</h1>
          <p className="mt-1 font-mono text-xs text-fg-faint break-all">{inv.input_url}</p>
        </div>
        <div className="flex items-center gap-3">
          <TierBadge tier={inv.overall_tier} size="lg" />
        </div>
      </header>

      {/* Metadata strip */}
      <Card>
        <CardLabel>Metadata</CardLabel>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3 text-sm">
          <Row label="Probability" value={`${Math.round(inv.overall_probability * 100)}%`} />
          <Row label="Batches"     value={String(inv.batch_count)} />
          <Row label="YT quota"    value={`${inv.quota_used} units`} />
          <Row label="Created"     value={new Date(inv.created_at).toLocaleString()} />
        </dl>
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
