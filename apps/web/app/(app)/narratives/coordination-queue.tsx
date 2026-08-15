'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight, ExternalLink, Loader2, RotateCw } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import {
  COORDINATION_FAMILY_LABEL,
  dismissCoordinationDetection,
  getCoordinationDetection,
  listCoordinationDetections,
  reopenCoordinationDetection,
  rerunCoordinationDetection,
  type CoordinationDetection,
  type CoordinationDetectionDetail,
  type CoordinationFilter,
  type CoordinationFinding,
} from '@/lib/api';

type View = CoordinationFilter | 'campaigns';

const VIEWS: { key: View; label: string }[] = [
  { key: 'campaigns', label: 'Campaigns' },
  { key: 'open', label: 'Open' },
  { key: 'dismissed', label: 'Dismissed' },
  { key: 'all', label: 'All' },
];

function when(iso: string | null): string {
  if (!iso) return 'unknown';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'unknown';
  const mins = Math.floor((Date.now() - t) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export function CoordinationQueue() {
  const [view, setView] = useState<View>('campaigns');
  const [rows, setRows] = useState<CoordinationDetection[] | null>(null);
  const [totals, setTotals] = useState<{ open: number; campaigns: number }>({
    open: 0,
    campaigns: 0,
  });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (v: View) => {
    setError(null);
    try {
      const res = await listCoordinationDetections(
        v === 'campaigns' ? { status: 'all', onlyCampaigns: true } : { status: v },
      );
      setRows(res.detections);
      setTotals({ open: res.open_count, campaigns: res.campaign_count });
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : 'Could not load detections.');
    }
  }, []);

  useEffect(() => {
    setRows(null);
    void load(view);
  }, [view, load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        {VIEWS.map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => setView(v.key)}
            className={cn(
              'h-8 px-3 rounded-md font-mono text-2xs uppercase tracking-wider ease-omi',
              'transition-[color,background-color,border-color] duration-150 border',
              view === v.key
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-border-2 text-fg-mute hover:text-fg-dim hover:border-border-hot',
            )}
          >
            {v.label}
            {v.key === 'campaigns' && totals.campaigns > 0 ? ` · ${totals.campaigns}` : ''}
            {v.key === 'open' && totals.open > 0 ? ` · ${totals.open}` : ''}
          </button>
        ))}
      </div>

      {error && (
        <Card className="border-danger/40">
          <p className="text-sm text-danger">{error}</p>
        </Card>
      )}

      {rows === null && (
        <Card>
          <p className="inline-flex items-center gap-2 text-sm text-fg-mute">
            <Loader2 size={14} className="animate-spin" /> Loading detections
          </p>
        </Card>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <Card>
          <p className="text-sm text-fg-dim">
            {view === 'campaigns'
              ? 'No corroborated coordination in anything scanned so far. That is the expected result most of the time, and it is a real finding rather than an empty page.'
              : 'Nothing here.'}
          </p>
        </Card>
      )}

      {rows?.map((d) => (
        <DetectionCard key={d.investigation_slug} row={d} onChanged={() => void load(view)} />
      ))}
    </div>
  );
}

function DetectionCard({
  row,
  onChanged,
}: {
  row: CoordinationDetection;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<CoordinationDetectionDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [failure, setFailure] = useState<string | null>(null);

  const expand = async () => {
    const next = !open;
    setOpen(next);
    if (next && !detail) {
      try {
        setDetail(await getCoordinationDetection(row.investigation_slug));
      } catch (e) {
        setFailure(e instanceof Error ? e.message : 'Could not load the evidence.');
      }
    }
  };

  const act = async (kind: 'rerun' | 'dismiss' | 'reopen') => {
    setBusy(kind);
    setFailure(null);
    try {
      const fn =
        kind === 'rerun'
          ? rerunCoordinationDetection(row.investigation_slug)
          : kind === 'dismiss'
            ? dismissCoordinationDetection(row.investigation_slug, note.trim())
            : reopenCoordinationDetection(row.investigation_slug);
      setDetail(await fn);
      onChanged();
    } catch (e) {
      setFailure(e instanceof Error ? e.message : 'That did not go through. Try again.');
    } finally {
      setBusy(null);
    }
  };

  const hasCampaign = row.campaign_count > 0;

  return (
    <Card className="space-y-4">
      {/* Stacked on mobile: a shrink-0 action cluster beside a flex-1 text column collapses that
          column to a couple of characters per line on a phone. */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-fg font-medium truncate">
            {row.investigation_label || row.investigation_slug}
          </p>
          <p className="font-mono text-2xs text-fg-mute mt-1 truncate">
            {row.platform} · {when(row.computed_at)} · pass {row.passes} · cohort cut on{' '}
            {row.score_source === 'analyst' ? 'OMI score' : 'engine score'}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span
            className={cn(
              'font-mono text-2xs uppercase tracking-wider',
              hasCampaign ? 'text-tier-high' : 'text-fg-mute',
            )}
          >
            {hasCampaign
              ? `${row.campaign_count} campaign${row.campaign_count === 1 ? '' : 's'}`
              : 'no campaign'}
          </span>
          <Link
            href={`/investigations/${row.investigation_slug}`}
            className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-dim hover:text-fg"
          >
            Investigation <ExternalLink size={11} />
          </Link>
        </div>
      </div>

      {/* The precondition the whole result rests on. Always visible: a reader who does not know
          how much of the batch was even eligible cannot judge what the finding means. */}
      <p className="text-sm text-fg-dim leading-relaxed">
        <span className="stat-value">{row.cohort_size}</span> of{' '}
        <span className="stat-value">{row.scanned_total}</span> scanned accounts scored 70 or above.
        Coordination was measured on those {row.cohort_size}; the timing and rarity tests used the
        whole batch.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => void expand()}
          className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-dim hover:text-fg"
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          {row.finding_count} finding{row.finding_count === 1 ? '' : 's'}
        </button>
        <span className="font-mono text-2xs text-fg-mute">
          strongest {pct(row.best_score)} · {row.best_label.replace(/_/g, ' ')}
        </span>
      </div>

      {failure && <p className="text-sm text-danger">{failure}</p>}

      {open && !detail && !failure && (
        <p className="inline-flex items-center gap-2 text-sm text-fg-mute">
          <Loader2 size={14} className="animate-spin" /> Loading the evidence
        </p>
      )}

      {open && detail && (
        <div className="space-y-4 border-t border-border-2 pt-4">
          {detail.findings.length === 0 && (
            <p className="text-sm text-fg-dim">
              Nothing linked these accounts to each other.
            </p>
          )}
          {detail.findings.map((f) => (
            <FindingBlock key={f.finding_id} finding={f} />
          ))}

          {detail.lone_high_scorers.length > 0 && (
            <p className="text-sm text-fg-mute leading-relaxed">
              <span className="stat-value">{detail.lone_high_scorers.length}</span> account
              {detail.lone_high_scorers.length === 1 ? '' : 's'} scored 70 or above with no link to
              anyone else here. Suspicious alone is not the same as acting together.
            </p>
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why this is or is not real (optional)"
              className="flex-1 min-w-0 h-9 px-3 rounded-md bg-bg-sunk border border-border-2 text-sm text-fg placeholder:text-fg-mute focus:outline-none focus:border-border-hot"
            />
            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="ghost"
                onClick={() => void act('rerun')}
                disabled={busy !== null}
              >
                {busy === 'rerun' ? (
                  <Loader2 size={13} className="animate-spin" />
                ) : (
                  <RotateCw size={13} />
                )}
                Re-run
              </Button>
              {detail.status === 'dismissed' ? (
                <Button variant="secondary" onClick={() => void act('reopen')} disabled={busy !== null}>
                  Reopen
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => void act('dismiss')} disabled={busy !== null}>
                  Dismiss
                </Button>
              )}
            </div>
          </div>
          <p className="font-mono text-2xs text-fg-mute">
            Re-running costs nothing: it reads the scan already stored, with no provider call and no
            credit. Dismissals are the only labelled negatives this detector ever gets.
          </p>
        </div>
      )}
    </Card>
  );
}

function FindingBlock({ finding }: { finding: CoordinationFinding }) {
  const isCampaign = finding.label === 'corroborated';
  return (
    <div className="rounded-lg border border-border-2 bg-bg-sunk p-4 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <span
            className={cn(
              'font-mono text-2xs uppercase tracking-wider',
              isCampaign ? 'text-tier-high' : 'text-tier-moderate',
            )}
          >
            {isCampaign ? 'Coordinated operation' : 'Lead, below the bar'}
          </span>
          <p className="text-sm text-fg mt-1.5">
            {finding.members.length} accounts ·{' '}
            <span className="stat-value">{pct(finding.score)}</span> probability
          </p>
          {/* The weakest-member framing is the honest one and has to be said, or a reader takes
              the headline number as applying evenly to everyone named. */}
          <p className="font-mono text-2xs text-fg-mute mt-1">
            every member is linked at this probability or better
          </p>
        </div>
        <span className="font-mono text-2xs text-fg-mute shrink-0">
          {pct(finding.density)} of pairs linked
        </span>
      </div>

      {finding.derivation && (
        <p className="font-mono text-2xs text-fg-mute leading-relaxed overflow-x-auto">
          {finding.derivation}
        </p>
      )}

      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {finding.members.map((m) => {
          const name = m.handle ? m.handle.replace(/^@/, '') : m.external_id;
          const own = finding.member_posteriors?.[name] ?? finding.member_posteriors?.[m.external_id];
          return (
            <span key={m.external_id} className="font-mono text-2xs text-fg-dim">
              @{name}
              {m.score !== null && <span className="text-fg-mute"> {Math.round(m.score)}</span>}
              {/* Each account's OWN probability, so a reviewer can challenge one name without
                  dismissing the whole finding. */}
              {own !== undefined && <span className="text-accent"> {pct(own)}</span>}
            </span>
          );
        })}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {finding.families_fired.map((f) => (
          <span key={f} className="font-mono text-2xs uppercase tracking-wider text-accent">
            {COORDINATION_FAMILY_LABEL[f] ?? f}
          </span>
        ))}
        {finding.families_silent.map((f) => (
          <span key={f} className="font-mono text-2xs uppercase tracking-wider text-fg-mute">
            {COORDINATION_FAMILY_LABEL[f] ?? f}: nothing
          </span>
        ))}
      </div>


      {finding.notes.map((n) => (
        <p key={n} className="text-sm text-fg-mute leading-relaxed">
          {n}
        </p>
      ))}

      {/* The quoted evidence. This is the point of the page: every claim names what the accounts
          themselves produced, so a reviewer can check it rather than trust a score. */}
      {finding.artifacts.length > 0 && (
        <div className="space-y-2 pt-1">
          {finding.artifacts.slice(0, 8).map((a, i) => (
            <div key={`${a.method}-${i}`} className="space-y-1">
              <p className="text-sm text-fg-dim leading-relaxed">{a.sentence}</p>
              <pre className="overflow-x-auto rounded bg-bg-elev border border-border-2 px-3 py-2 font-mono text-2xs text-fg-mute whitespace-pre-wrap break-words">
                {a.artifact}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
