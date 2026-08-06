'use client';

import { AnalysisProgress } from '@/components/shared/analysis-progress';

/**
 * The analyst's loading screen, now a thin wrapper over the ONE progress component the whole
 * investigation flow shares (`components/shared/analysis-progress.tsx`).
 *
 * It used to be its own design. That is how a user ended up watching three different loading
 * screens for one job: this card, the violet "Analyzing N accounts" card on the select page, and
 * the grey route skeleton in between. Keep the visuals in the shared component so a change to one
 * step cannot silently make the flow look like three.
 */
export function AnalystLoading({
  elapsedSec,
  accounts,
  totalBatches,
  retrying = false,
}: {
  elapsedSec: number;
  accounts?: number;
  totalBatches?: number;
  retrying?: boolean;
}) {
  return (
    <AnalysisProgress
      elapsedSec={elapsedSec}
      accounts={accounts}
      totalBatches={totalBatches}
      phase="analysing"
      retrying={retrying}
    />
  );
}
