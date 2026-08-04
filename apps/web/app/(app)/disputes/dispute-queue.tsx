'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ExternalLink, Loader2, Mail, ShieldOff } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import {
  listDisputes,
  resolveDispute,
  type DisputeStatus,
  type ReportDispute,
} from '@/lib/api';

type Filter = DisputeStatus | 'all';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'open', label: 'Open' },
  { key: 'reviewing', label: 'Reviewing' },
  { key: 'upheld', label: 'Upheld' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all', label: 'All' },
];

/** Status colour carries meaning, not decoration: open is work outstanding, upheld means we were
 *  wrong about someone. Plain mono spans rather than pills (components/ui/badge.tsx is deleted). */
const STATUS_TONE: Record<DisputeStatus, string> = {
  open: 'text-tier-high',
  reviewing: 'text-tier-elevated',
  upheld: 'text-accent-2',
  rejected: 'text-fg-mute',
};

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

export function DisputeQueue() {
  const [filter, setFilter] = useState<Filter>('open');
  const [rows, setRows] = useState<ReportDispute[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (f: Filter) => {
    setError(null);
    try {
      setRows(await listDisputes(f));
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : 'Could not load the queue.');
    }
  }, []);

  useEffect(() => {
    setRows(null);
    void load(filter);
  }, [filter, load]);

  const onResolved = (updated: ReportDispute) => {
    setRows((prev) => {
      if (!prev) return prev;
      // Drop it from a filtered view it no longer belongs in, so the queue reads as work remaining.
      if (filter !== 'all' && updated.status !== filter) {
        return prev.filter((r) => r.id !== updated.id);
      }
      return prev.map((r) => (r.id === updated.id ? updated : r));
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => setFilter(f.key)}
            className={cn(
              'h-8 px-3 rounded-md font-mono text-2xs uppercase tracking-wider ease-omi',
              'transition-[color,background-color,border-color] duration-150 border',
              filter === f.key
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-border-2 text-fg-mute hover:text-fg-dim hover:border-border-hot',
            )}
          >
            {f.label}
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
            <Loader2 size={14} className="animate-spin" /> Loading the queue
          </p>
        </Card>
      )}

      {rows !== null && rows.length === 0 && !error && (
        <Card>
          <p className="text-sm text-fg-dim">
            {filter === 'open'
              ? 'Nothing outstanding. Every filed dispute has been resolved.'
              : 'No disputes with this status.'}
          </p>
        </Card>
      )}

      {rows?.map((d) => (
        <DisputeCard key={d.id} dispute={d} onResolved={onResolved} />
      ))}
    </div>
  );
}

function DisputeCard({
  dispute,
  onResolved,
}: {
  dispute: ReportDispute;
  onResolved: (d: ReportDispute) => void;
}) {
  const [note, setNote] = useState(dispute.resolution_note ?? '');
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmingTakedown, setConfirmingTakedown] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const act = async (status: DisputeStatus, unpublish = false) => {
    setBusy(unpublish ? 'takedown' : status);
    setFailure(null);
    try {
      onResolved(await resolveDispute(dispute.id, { status, note: note.trim() || undefined, unpublish }));
    } catch (e) {
      setFailure(e instanceof Error ? e.message : 'That did not go through. Try again.');
    } finally {
      setBusy(null);
      setConfirmingTakedown(false);
    }
  };

  return (
    <Card className="space-y-4">
      {/* Header. Stacked on mobile: a shrink-0 action cluster beside a flex-1 text column
          collapses the text to a couple of characters per line on a phone. */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-fg">
            <span className="font-medium">
              {dispute.subject_handle ? `@${dispute.subject_handle.replace(/^@/, '')}` : 'Account not named'}
            </span>
            <span className="text-fg-mute"> disputes this report</span>
          </p>
          <p className="font-mono text-2xs text-fg-mute mt-1 truncate">
            #{dispute.id} · {when(dispute.created_at)} · token {dispute.share_token}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className={cn('font-mono text-2xs uppercase tracking-wider', STATUS_TONE[dispute.status])}>
            {dispute.status}
          </span>
          {dispute.report_still_public ? (
            <Link
              href={`/r/${dispute.share_token}`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-dim hover:text-fg"
            >
              Open report <ExternalLink size={11} />
            </Link>
          ) : (
            <span className="inline-flex items-center gap-1 font-mono text-2xs uppercase tracking-wider text-fg-mute">
              <ShieldOff size={11} /> Unpublished
            </span>
          )}
        </div>
      </div>

      <p className="text-sm text-fg-dim leading-relaxed whitespace-pre-wrap break-words">
        {dispute.reason}
      </p>

      {dispute.contact && (
        <p className="inline-flex items-center gap-1.5 font-mono text-2xs text-fg-mute break-all">
          <Mail size={11} className="shrink-0" />
          <a href={`mailto:${dispute.contact}`} className="hover:text-fg-dim">{dispute.contact}</a>
        </p>
      )}

      {failure && <p className="text-xs text-danger">{failure}</p>}

      <div className="space-y-2.5 pt-1 border-t border-border-1">
        <label className="block pt-3">
          <span className="font-mono text-2xs uppercase tracking-wider text-fg-mute">
            Resolution note
          </span>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="What did you check, and what did you conclude?"
            className="mt-1.5 w-full rounded-md border border-border-2 bg-bg-elev-2 px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent/50"
          />
        </label>

        <div className="flex flex-wrap gap-2">
          {dispute.status === 'open' && (
            <Button
              variant="secondary"
              size="sm"
              disabled={busy !== null}
              onClick={() => act('reviewing')}
            >
              {busy === 'reviewing' && <Loader2 size={13} className="animate-spin" />}
              Start review
            </Button>
          )}

          {/*
            The takedown. Two clicks on purpose: revoking clears the share token, so /r/<token> 404s
            for every link already posted publicly and re-sharing mints a different one. That is the
            correct outcome when we got someone wrong, and the wrong one to reach by a stray click.
          */}
          {confirmingTakedown ? (
            <>
              <Button
                variant="danger"
                size="sm"
                disabled={busy !== null}
                onClick={() => act('upheld', true)}
              >
                {busy === 'takedown' && <Loader2 size={13} className="animate-spin" />}
                Confirm: unpublish permanently
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={busy !== null}
                onClick={() => setConfirmingTakedown(false)}
              >
                Cancel
              </Button>
            </>
          ) : (
            <Button
              variant="danger"
              size="sm"
              disabled={busy !== null || !dispute.report_still_public}
              onClick={() => setConfirmingTakedown(true)}
            >
              <AlertTriangle size={13} /> Uphold and take down
            </Button>
          )}

          <Button
            variant="secondary"
            size="sm"
            disabled={busy !== null}
            onClick={() => act('upheld')}
          >
            {busy === 'upheld' && <Loader2 size={13} className="animate-spin" />}
            Uphold, leave published
          </Button>

          <Button
            variant="ghost"
            size="sm"
            disabled={busy !== null}
            onClick={() => act('rejected')}
          >
            {busy === 'rejected' && <Loader2 size={13} className="animate-spin" />}
            Reject
          </Button>
        </div>

        {confirmingTakedown && (
          <p className="text-xs text-fg-mute leading-relaxed">
            This revokes the share link immediately, including for links already posted publicly. The
            investigation itself is kept: the customer keeps their work, and what is withdrawn is the
            public claim. Re-sharing later produces a different link.
          </p>
        )}
      </div>
    </Card>
  );
}
