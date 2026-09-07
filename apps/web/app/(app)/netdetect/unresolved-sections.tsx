'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { netdetectSections, reviewNetdetectSection, type NetdetectSection } from '@/lib/api';

/**
 * Sections the scan could not resolve.
 *
 * WHY THIS PANEL EXISTS AT ALL. A finding queue can only ever show what the detector named. An
 * operation that owns more than about a quarter of a comment section pushes its own provisioning
 * and targeting evidence past the rarity ceiling, so it is discarded before any statistics run and
 * the scan produces NO findings. Measured, recall falls from 8/8 to zero between 24% and 32% share.
 * Without this panel that section is invisible: an empty queue and a clean queue look identical,
 * and the more of a post an operation owns the safer it is.
 *
 * IT NAMES NO ACCOUNTS, and that is not squeamishness. The group failed the significance test, and
 * the statistic that flagged the section fires just as hard on a fan community filling a small
 * section, because a null built from a section one group dominates cannot resolve that group in
 * either direction. Naming anyone would publish a claim the evidence could not support. What the
 * panel gives an operator is the shape and the next step.
 */
export function UnresolvedSections() {
  const [rows, setRows] = useState<NetdetectSection[] | null>(null);
  const [note, setNote] = useState('');
  const [failed, setFailed] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const body = await netdetectSections('open');
      setRows(body.sections);
      setNote(body.note);
    } catch (e) {
      // A panel that cannot load must not take the page with it: the finding queue below is the
      // work, and this is a warning about what the work could not cover.
      setRows([]);
      setFailed(e instanceof Error ? e.message : 'Could not load unresolved sections.');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Nothing to say is the ordinary case, and an empty panel here would be noise on every visit.
  if (rows !== null && rows.length === 0) return null;

  return (
    <Card className="border-tier-elevated/30 space-y-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-tier-elevated" aria-hidden />
        <div className="min-w-0">
          <p className="meta meta-hi">Could not resolve</p>
          <p className="mt-1 text-xs text-fg-dim">{note}</p>
        </div>
      </div>

      {failed ? <p className="text-xs text-tier-high">{failed}</p> : null}

      {rows === null ? (
        <div className="flex items-center gap-2 text-sm text-fg-mute">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading
        </div>
      ) : (
        rows.map((row) => <SectionRow key={row.id} row={row} onReviewed={() => void load()} />)
      )}
    </Card>
  );
}

function SectionRow({ row, onReviewed }: { row: NetdetectSection; onReviewed: () => void }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  const review = async () => {
    const text = note.trim();
    // The API rejects a blank note. A verdict with no stated reason records that somebody looked
    // and nothing about what they concluded, which is the one thing this reservoir cannot use.
    if (!text) {
      setFailed('Say what this section turned out to be.');
      return;
    }
    setBusy(true);
    setFailed(null);
    try {
      await reviewNetdetectSection(row.id, text);
      onReviewed();
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Could not record that.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-l-2 border-tier-elevated pl-2.5 space-y-2">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="meta meta-hi">
          {row.group_size} of {row.corpus_size} accounts
        </span>
        <span className="meta">{row.families.join(" · ") || 'no family'}</span>
        <span className="meta">up to {Math.round(row.top_prevalence * 100)}% of the section</span>
      </div>
      <p className="font-mono text-xs text-fg-mute break-all">
        {row.context_id ? `post ${row.context_id}` : 'no post recorded'}
      </p>
      <p className="text-xs text-fg-dim">{row.sentence}</p>

      <CatalogueVerdict row={row} />

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="A fan community. / Swept it: two accounts placed in a known operation."
          className="h-9 flex-1 min-w-0 rounded-md border border-border-1 bg-bg-inset px-2.5 text-sm text-fg placeholder:text-fg-mute focus-hard"
        />
        <Button size="sm" variant="secondary" onClick={review} disabled={busy}>
          {busy ? 'Recording' : 'I looked'}
        </Button>
      </div>
      {failed ? <p className="text-xs text-tier-high">{failed}</p> : null}
    </div>
  );
}

/**
 * What the formation catalogue could say about a section that could not resolve itself.
 *
 * THIS IS THE LEAD, and it is the difference between a queue of dead ends and a queue of work.
 * "Could not resolve" leaves an operator with nothing to do; "could not resolve, and the catalogue
 * places 8 of these accounts in a known operation" is somewhere to start.
 *
 * IT BRANCHES ON `catalogue_checked`, NEVER ON THE COUNT. Three states report zero placements and
 * they are opposite statements about named people: never consulted, nothing catalogued to compare
 * against, and consulted with no match. Same discipline as `attachment_checked` on a finding.
 *
 * NO NAMES. A placement is a claim about a person and belongs in the sweep panel below, which
 * renders the evidence a reader needs to argue with it. This is a count and a pointer.
 */
function CatalogueVerdict({ row }: { row: NetdetectSection }) {
  if (!row.catalogue_checked) {
    return (
      <p className="text-xs text-fg-mute">
        The formation catalogue was not consulted for this section.
      </p>
    );
  }
  if (row.catalogue_empty) {
    return (
      <p className="text-xs text-fg-mute">
        Nothing has been catalogued yet, so there was nothing to weigh these accounts against. That
        is not the same as finding no match.
      </p>
    );
  }
  if (row.catalogue_placed === 0) {
    return (
      <p className="text-xs text-fg-mute">
        No account here matched a known operation. The catalogue only recognises operations somebody
        has already recorded, so this is not a clean section.
      </p>
    );
  }
  return (
    <p className="text-xs text-tier-elevated">
      The formation catalogue places{' '}
      <span className="font-mono">{row.catalogue_placed}</span>{' '}
      {row.catalogue_placed === 1 ? 'account' : 'accounts'} here in an operation recorded in another
      investigation
      {row.catalogue_concealed > 0 ? (
        <>
          , <span className="font-mono">{row.catalogue_concealed}</span> of which would have passed
          an individual review
        </>
      ) : null}
      . Sweep this investigation to see which.
    </p>
  );
}
