'use client';

import { useState } from 'react';
import { type CommenterScanResult, type ComprehensiveScanResult } from '@/lib/api';
import { CommenterList } from '../../investigate/commenter-list';
import { CommenterDetail } from '../../investigate/commenter-detail';
import { Synthesis } from '../../investigate/synthesis';
import { InsightsRail } from '../../investigate/insights-rail';

/**
 * Read-only viewer for a saved investigation. Same three-pane layout as
 * the live workspace, just driven by a stored payload instead of a
 * fresh scan.
 */
export function SavedInvestigationViewer({ payload }: { payload: ComprehensiveScanResult }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const commenters = payload.video?.commenters || [];
  const selected: CommenterScanResult | null =
    commenters.find((c) => c.external_id === selectedId) || null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr_360px] gap-4 min-h-[640px]">
      <div className="bg-bg-elev border border-border-1 rounded-md overflow-hidden">
        {commenters.length > 0 ? (
          <CommenterList
            commenters={commenters}
            selectedId={selectedId}
            onSelect={(c) => setSelectedId(c.external_id)}
          />
        ) : (
          <div className="p-4 font-mono text-2xs text-fg-mute uppercase tracking-wider">
            No commenter list — channel-only investigation.
          </div>
        )}
      </div>

      <div className="bg-bg-elev border border-border-1 rounded-md overflow-hidden flex flex-col min-w-0">
        <div className="flex-1 overflow-y-auto">
          {selected ? <CommenterDetail c={selected} /> : <Synthesis data={payload} />}
        </div>
      </div>

      <div className="bg-bg-elev border border-border-1 rounded-md overflow-hidden">
        <InsightsRail crossLinks={payload.cross_links || []} />
      </div>
    </div>
  );
}
