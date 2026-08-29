'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Check, Loader2, ShieldQuestion, X } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import { hasHolderData } from '@/lib/evidence-matrix';
import { EvidenceMatrix } from './evidence-matrix';
import {
  judgeNetdetectFinding,
  listNetdetectFindings,
  netdetectCalibration,
  type NetdetectFinding,
  type NetdetectNextToJudge,
  type NetdetectStatus,
} from '@/lib/api';

type Filter = NetdetectStatus | 'all';

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'open', label: 'Open' },
  { key: 'confirmed', label: 'Confirmed' },
  { key: 'dismissed', label: 'Dismissed' },
  { key: 'all', label: 'All' },
];

type RankedFinding = NetdetectNextToJudge & { rank: number };

type Ranking = { order: NetdetectNextToJudge[]; stillNeeded: string };

/** Open is work outstanding; confirmed is the rarer and more valuable label. */
const STATUS_TONE: Record<NetdetectStatus, string> = {
  open: 'text-tier-elevated',
  confirmed: 'text-tier-high',
  dismissed: 'text-fg-mute',
};

export function FindingQueue() {
  const [filter, setFilter] = useState<Filter>('open');
  const [rows, setRows] = useState<NetdetectFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ranking, setRanking] = useState<Ranking | null>(null);

  const load = useCallback(async (f: Filter) => {
    setError(null);
    try {
      setRows(await listNetdetectFindings(f));
    } catch (e) {
      setRows([]);
      setError(e instanceof Error ? e.message : 'Could not load the queue.');
    }
  }, []);

  useEffect(() => {
    setRows(null);
    void load(filter);
  }, [filter, load]);

  // The ranking is a convenience over the queue and must never be able to hide it: a failure here
  // leaves `ranking` null and every finding renders in the order the API returned, unmarked.
  useEffect(() => {
    let live = true;
    netdetectCalibration()
      .then((c) => {
        if (live) setRanking({ order: c.next_to_judge, stillNeeded: c.still_needed });
      })
      .catch(() => {
        if (live) setRanking(null);
      });
    return () => {
      live = false;
    };
  }, []);

  // Ranked first, in rank order, then everything else in the order the API gave. Only on the open
  // filter: confirmed and dismissed are a record rather than a work queue, and reordering a record
  // by how much it would teach makes no sense.
  const ranks = new Map((ranking?.order ?? []).map((n, i) => [n.finding_id, { ...n, rank: i + 1 }]));
  const ordered =
    rows && filter === 'open' && ranks.size > 0
      ? [...rows].sort(
          (a, b) =>
            (ranks.get(a.id)?.rank ?? Number.MAX_SAFE_INTEGER) -
            (ranks.get(b.id)?.rank ?? Number.MAX_SAFE_INTEGER),
        )
      : rows;

  const onJudged = (updated: NetdetectFinding) => {
    setRows((prev) => {
      if (!prev) return prev;
      // Drop it from a filtered view it no longer belongs in, so "Open" reads as work remaining
      // rather than as a log of everything ever looked at.
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
              'transition-[color,background-color,border-color] duration-150 border focus-hard',
              filter === f.key
                ? 'border-accent/40 bg-accent/10 text-accent'
                : 'border-border-1 text-fg-mute hover:text-fg',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {error ? (
        <Card className="border-tier-high/30">
          <p className="text-sm text-tier-high">{error}</p>
        </Card>
      ) : null}

      {filter === 'open' && ranking && ranks.size > 0 ? <JudgeFirstNote ranking={ranking} /> : null}

      {rows === null ? (
        <div className="flex items-center gap-2 text-fg-mute text-sm">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          Loading findings
        </div>
      ) : rows.length === 0 ? (
        <Card>
          <p className="text-sm text-fg-mute">
            Nothing here. Run the detector on an investigation from{' '}
            <code className="font-mono text-2xs">POST /v1/admin/netdetect/&lt;slug&gt;</code> and its
            findings arrive in this queue.
          </p>
        </Card>
      ) : (
        (ordered ?? rows).map((row) => (
          <FindingCard key={row.id} row={row} onJudged={onJudged} next={ranks.get(row.id) ?? null} />
        ))
      )}
    </div>
  );
}

/** The ranking, plus what the reservoir still needs, as one small statement above the queue. */
function JudgeFirstNote({ ranking }: { ranking: Ranking }) {
  return (
    <Card className="border-accent/25 space-y-1.5">
      <p className="meta meta-hi">Judge these first</p>
      <p className="text-xs text-fg-dim">
        {/* THE ORDER IS INFORMATION, NOT SUSPICION, and an operator who reads it the other way works
            the borderline cases believing them to be the most damning. The sentence says so in the
            one place the ordering is actually visible, because the caveat on the API response is not
            somewhere anyone reads. */}
        The top {ranking.order.length} finding{ranking.order.length === 1 ? '' : 's'} below{' '}
        {ranking.order.length === 1 ? 'sits' : 'sit'} nearest a threshold that is being fitted, so a
        verdict on {ranking.order.length === 1 ? 'it' : 'them'} changes what the calibration report
        can recommend. This is not a strength order and it is close to the opposite of one: a group
        reported whatever the thresholds are set to teaches nothing, because nobody needed a label to
        know how it would come out. Every other finding here is equally worth judging on its merits.
      </p>
      {ranking.stillNeeded ? (
        <p className="font-mono text-2xs text-fg-mute">Still needed: {ranking.stillNeeded}</p>
      ) : (
        <p className="font-mono text-2xs text-fg-mute">
          The reservoir is deep enough to fit against. The calibration report recommends from here.
        </p>
      )}
    </Card>
  );
}

function FindingCard({
  row,
  onJudged,
  next,
}: {
  row: NetdetectFinding;
  onJudged: (r: NetdetectFinding) => void;
  next: RankedFinding | null;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState<'dismiss' | 'confirm' | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  const judge = async (verdict: 'dismiss' | 'confirm') => {
    const text = reason.trim();
    // The reason is required and is the entire point: a judgement with none records that somebody
    // was unconvinced and nothing about why, which cannot be fitted against later. The API rejects
    // a blank one too; this only saves the round trip.
    if (!text) {
      setFailed('Say why. The reason is the only thing a later calibration can be fitted against.');
      return;
    }
    setBusy(verdict);
    setFailed(null);
    try {
      onJudged(await judgeNetdetectFinding(row.id, verdict, text));
    } catch (e) {
      setFailed(e instanceof Error ? e.message : 'Could not record that.');
    } finally {
      setBusy(null);
    }
  };

  const weak = new Set(row.weakly_attached);
  const matrixed = hasHolderData(row.evidence);

  return (
    <Card className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="meta meta-hi">{row.member_count} accounts</span>
            <span className={cn('font-mono text-2xs uppercase tracking-wider', STATUS_TONE[row.status])}>
              {row.status}
            </span>
            <span className="meta">{row.platform}</span>
            {next ? (
              // Deliberately says what it means rather than a bare number: "#1" beside an account
              // set reads as a strength rank, which is the one thing this ordering is not.
              <span
                className="font-mono text-2xs uppercase tracking-wider text-accent"
                title={next.why}
              >
                #{next.rank} moves {next.flips_constants} threshold
                {next.flips_constants === 1 ? '' : 's'}
              </span>
            ) : null}
          </div>
          <p className="mt-1 font-mono text-xs text-fg-mute break-all">
            {row.context_id ? `post ${row.context_id}` : 'no post recorded'}
          </p>
        </div>
        <div className="flex gap-4 shrink-0">
          <Readout label="Score" value={row.score.toFixed(2)} />
          <Readout
            label="Corrected p"
            /* Null means "not compared against the shuffled search", which is not the same as
               passing it, so it renders as a dash rather than as a number. */
            value={row.corrected_p === null ? '-' : row.corrected_p.toFixed(3)}
          />
          <Readout label="Corpus" value={String(row.corpus_size)} />
        </div>
      </div>

      {row.needs_adjudication ? (
        <div className="flex gap-2 rounded-md border border-tier-elevated/30 bg-tier-elevated/5 p-3">
          <ShieldQuestion className="h-4 w-4 shrink-0 text-tier-elevated" aria-hidden />
          <p className="text-xs text-fg-dim">{row.needs_adjudication}</p>
        </div>
      ) : null}

      {/* ONE member list, not two. When holders were recorded the matrix's row labels ARE the
          member list, marked the same way; the chip row is the fallback for findings stored before
          the join existed. The three-state sentence below belongs to both. */}
      <div>
        {matrixed ? (
          <EvidenceMatrix
            members={row.members}
            evidence={row.evidence}
            weaklyAttached={row.weakly_attached}
          />
        ) : (
          <>
            <p className="meta mb-1.5">Members</p>
            <div className="flex flex-wrap gap-1.5">
              {row.members.map((m) => (
                <span
                  key={m}
                  className={cn(
                    'font-mono text-2xs px-1.5 py-0.5 rounded-sm border',
                    weak.has(m)
                      ? 'border-tier-elevated/40 text-tier-elevated'
                      : 'border-border-1 text-fg-dim',
                  )}
                  title={weak.has(m) ? 'Does not carry this finding. Still a member; check it first.' : undefined}
                >
                  {m}
                </span>
              ))}
            </div>
          </>
        )}
        <p className="mt-1.5 text-2xs text-fg-mute">
          {/* THREE STATES, and the middle one is easy to lose. An empty list means opposite things
              with and without `attachment_checked`, so the sentence never leaves it to inference. */}
          {!row.attachment_checked
            ? `Membership was not tested${row.attachment_note ? `: ${row.attachment_note}` : '.'}`
            : row.weakly_attached.length > 0
              ? `${row.weakly_attached.length} highlighted member${row.weakly_attached.length === 1 ? '' : 's'} did not carry this finding. They are still members; check those names against the evidence first.`
              : 'Every member carries this finding.'}
        </p>
      </div>

      {/* PRIOR HISTORY, and the reason only one of its numbers is shown.
          `log_lr` is measured NOT to separate an operation from a newsroom (both saturate the cap,
          and the newsroom carried more linked pairs), so putting it beside a finding would read as
          corroborating evidence while discriminating nothing. `hard_pairs` is prior evidence of the
          operator's own acts, which is the half that does separate them, so that is what is stated.
          A finding with no lookup renders nothing rather than "not seen before": those are opposite
          claims about the people named, the same distinction as `attachment_checked`. */}
      {row.corroboration && row.corroboration.checked ? (
        <div
          className={
            // `.rule-rack` is `height: 1px`: a hairline RULE, not a frame. It was collapsing this
            // block to 1px and spilling its text over the evidence beneath it. The left rule is
            // the treatment that was actually wanted and it stands on its own.
            row.corroboration.hard_pairs > 0
              ? 'border-l-2 border-tier-high pl-2.5'
              : 'border-l-2 border-border-1 pl-2.5'
          }
        >
          <p className="meta mb-1">Seen before</p>
          <p className="text-xs text-fg-dim">{row.corroboration.sentence}</p>
        </div>
      ) : null}

      {/* The matrix carries the SHAPE; these carry the QUOTE. A grid cannot be screenshotted into
          a sentence, and "if you cannot quote it, you cannot claim it" applies to a coordination
          claim as much as to the analyst's prose, so the strongest few stay written out. */}
      {row.evidence.length > 0 ? (
        <div>
          <p className="meta mb-1.5">Strongest evidence</p>
          <ul className="space-y-1">
            {row.evidence.slice(0, 4).map((e, i) => (
              <li key={i} className="text-xs text-fg-dim">
                <span className="meta mr-1.5">{e.family}</span>
                {e.sentence}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {row.status === 'open' ? (
        <div className="space-y-2 border-t border-border-1 pt-3">
          <label className="meta block" htmlFor={`reason-${row.id}`}>
            Why
          </label>
          <textarea
            id={`reason-${row.id}`}
            value={reason}
            onChange={(ev) => setReason(ev.target.value)}
            rows={2}
            placeholder="These are reporters on one beat. / Same script under four unrelated posts, checked by hand."
            className={cn(
              'w-full rounded-md border border-border-1 bg-bg px-3 py-2 text-sm',
              'placeholder:text-fg-mute focus-hard',
            )}
          />
          {failed ? <p className="text-xs text-tier-high">{failed}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => judge('confirm')} disabled={busy !== null}>
              {busy === 'confirm' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <Check className="h-3.5 w-3.5" aria-hidden />
              )}
              This is real
            </Button>
            <Button variant="ghost" onClick={() => judge('dismiss')} disabled={busy !== null}>
              {busy === 'dismiss' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              ) : (
                <X className="h-3.5 w-3.5" aria-hidden />
              )}
              Not an operation
            </Button>
          </div>
        </div>
      ) : row.dismissal_reason ? (
        <div className="flex gap-2 border-t border-border-1 pt-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-fg-mute" aria-hidden />
          <p className="text-xs text-fg-dim">{row.dismissal_reason}</p>
        </div>
      ) : null}
    </Card>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="readout-v">
      <span className="meta">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}
