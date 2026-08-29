'use client';

import { useState } from 'react';
import { cn } from '@/lib/cn';
import {
  FAMILY_MEANING,
  buildEvidenceMatrix,
  shapeOf,
  type MatrixColumn,
} from '@/lib/evidence-matrix';
import type { NetdetectEvidence } from '@/lib/api';

/**
 * The finding drawn as what it is: members down the side, the evidence across the top.
 *
 * WHY A GRID AND NOT A GRAPH. The whole thesis of this detector is that a set-level statistic is
 * not recoverable by fusing pairwise ones, so a force-directed account graph would draw the wrong
 * object confidently: it shows edges the score was never computed from. The incidence matrix IS the
 * evidence, and it answers the question a reviewer actually has about a group of named real people,
 * which is not "how strong is this" but "are these the same people throughout".
 *
 * COLOUR IS A FACT HERE, NOT A SCORE. A filled cell says this account holds this feature. Painting
 * it on the tier ramp would say this account is more suspicious, which no single cell can support,
 * so hard families take the identity blue and soft families the neutral ramp: the encoding is WHICH
 * KIND of evidence, which is the thing that discriminates. The only tier colour on the grid is the
 * existing `weakly_attached` marker, which comes from leave-one-out set surprise rather than from
 * anything visible in the row.
 */
export function EvidenceMatrix({
  members,
  evidence,
  weaklyAttached,
  handles,
}: {
  members: string[];
  evidence: NetdetectEvidence[];
  weaklyAttached: string[];
  handles?: Record<string, string>;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const matrix = buildEvidenceMatrix(members, evidence, weaklyAttached);

  // THREE STATES, and the middle one is the easy one to lose. An empty grid would say these
  // accounts share nothing, which cannot be true of a finding that exists at all.
  if (!matrix.recorded) {
    return (
      <div>
        <p className="meta mb-1.5">Evidence matrix</p>
        <p className="text-2xs text-fg-mute">
          Which member holds which feature was not recorded for this finding. Re-run the detector on
          this investigation to fill it in. The evidence below is unaffected.
        </p>
      </div>
    );
  }

  const shape = shapeOf(matrix);
  const active = hover === null ? null : matrix.columns[hover];

  return (
    <div>
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="meta meta-hi">Evidence matrix</p>
        <p className="meta">
          {matrix.rows.length} accounts · {matrix.columns.length} features ·{' '}
          {matrix.familyCount} famil{matrix.familyCount === 1 ? 'y' : 'ies'}
        </p>
      </div>

      {/* THE OPERATOR'S OWN ACTS, STATED WHETHER OR NOT THEY ARE THERE.
          A band that contributes nothing draws nothing, and a reader cannot notice a column that
          was never rendered. Measured, the professional-beat control (ten reporters on one beat,
          the population this detector most owes an accurate reading) comes back as a SOLID block
          with zero identity and zero network features, and the solid block is the alarming part.
          So the absence is printed rather than left to inference. Hollow is "none", which is the
          same encoding the grid uses, so no value judgement is smuggled in through colour. */}
      <div className="mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="meta">Operator&apos;s own acts</span>
        {matrix.hardPresence.map((h) => (
          <span key={h.family} className="flex items-center gap-1.5">
            <span
              className={cn(
                'h-2.5 w-2.5 rounded-[1px] border',
                h.columns > 0 ? 'border-accent bg-accent' : 'border-border-2 bg-transparent',
              )}
              aria-hidden
            />
            <span
              className={cn(
                'font-mono text-[10px] uppercase tracking-wider',
                h.columns > 0 ? 'text-accent' : 'text-fg-mute',
              )}
            >
              {h.family} {h.columns > 0 ? `${h.columns}` : 'none'}
            </span>
          </span>
        ))}
      </div>

      {/* Wide content scrolls inside its OWN container. The page is a column, never a canvas.
          NOT `.rule-rack` here: that class is `height: 1px`, a hairline RULE rather than a frame,
          and using it as a container collapses the box and spills its content over whatever
          follows. Measured at 1px tall with the grid overflowing it. */}
      <div className="overflow-x-auto border-y border-border-1 py-1.5">
        <div className="inline-block min-w-full align-top">
          {/* Family bands: how many kinds of evidence, how wide each one is, and which of them
              only an operator produces. Those three shapes ARE the three refusals, which are
              otherwise only ever stated as a sentence after the fact: `MIN_FAMILIES` is how many
              bands have any fill, `MAX_SINGLE_FAMILY_SHARE` is one band dwarfing the rest, and
              `MIN_HARD_EVIDENCE` is whether the hard bands hold anything at all.

              The header lays out with the SAME cells as the rows, drawn at zero height, rather
              than computing a width from the cell size. A band header whose width is a magic
              number drifts silently the first time a cell changes size, and a misaligned column
              header on a grid about named people mislabels the evidence against them. */}
          <div className="flex items-end gap-2 pl-[104px]">
            {matrix.bands.map((band) => (
              <div
                key={band.family}
                className="min-w-0 shrink-0"
                title={FAMILY_MEANING[band.family] ?? band.family}
              >
                <div
                  className={cn(
                    'truncate font-mono text-[9px] uppercase tracking-wider',
                    band.hard ? 'text-accent' : 'text-fg-mute',
                  )}
                >
                  {/* A one-column band is 12px wide and "infrastructure" truncates to "I...",
                      which is noise rather than a label. Shorten to what fits; the full name is on
                      the title, in the hover caption, and spelled out for the two hard families in
                      the strip above. */}
                  {bandLabel(band.family, band.columns.length)}
                </div>
                <div
                  className={cn('h-px', band.hard ? 'bg-accent' : 'bg-border-2')}
                  aria-hidden
                />
                <div className="flex gap-px" aria-hidden>
                  {band.columns.map((col) => (
                    <div key={col.index} className="h-0 w-3 shrink-0" />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {matrix.rows.map((row) => (
            <div key={row.member} className="flex items-center gap-2">
              <div
                className={cn(
                  'w-[100px] shrink-0 truncate pr-1 text-right font-mono text-[10px]',
                  row.weak ? 'text-tier-elevated' : 'text-fg-dim',
                )}
                title={
                  row.weak
                    ? `${handles?.[row.member] ?? row.member}: does not carry this finding. Still a member; check it first.`
                    : (handles?.[row.member] ?? row.member)
                }
              >
                {handles?.[row.member] ?? row.member}
              </div>
              {matrix.bands.map((band) => (
                <div key={band.family} className="flex shrink-0 items-center gap-px">
                  {band.columns.map((col) => (
                    <div
                      key={col.index}
                      onMouseEnter={() => setHover(col.index)}
                      onMouseLeave={() => setHover(null)}
                      className={cn(
                        'h-3 w-3 shrink-0 rounded-[1px] border',
                        'transition-colors duration-150 ease-omi',
                        // SOLID TOKENS ONLY. Tailwind generates no opacity variant for a colour
                        // declared as a bare `var(--x)`, so `bg-accent/70` lands in the class list
                        // and never in the stylesheet: measured, every cell computed to
                        // transparent and the whole grid rendered hollow.
                        row.cells[col.index]
                          ? col.hard
                            ? 'border-accent bg-accent'
                            : 'border-border-hot bg-border-hot'
                          : 'border-border-1 bg-transparent',
                        hover === col.index && 'ring-1 ring-accent-2',
                      )}
                      title={`${handles?.[row.member] ?? row.member} ${row.cells[col.index] ? 'holds' : 'does not hold'}: ${col.sentence}`}
                    />
                  ))}
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* One row of prose for the hovered column, so the grid is readable without a legend the
          reader has to memorise. Reserved height, or the card jumps as the pointer moves. */}
      <p className="mt-1.5 min-h-[2.25em] text-2xs text-fg-dim">
        {active ? <ColumnCaption col={active} /> : (shape ?? <LegendLine />)}
      </p>
    </div>
  );
}

/** Roughly 6px per character at 9px mono with this tracking, measured against the rendered grid. */
function bandLabel(family: string, columns: number): string {
  const room = Math.floor((columns * 13) / 6);
  return family.length <= room ? family : family.slice(0, Math.max(2, room));
}

function ColumnCaption({ col }: { col: MatrixColumn }) {
  return (
    <>
      <span className={cn('meta mr-1.5', col.hard && 'text-accent')}>{col.family}</span>
      {col.sentence}{' '}
      <span className="text-fg-mute">
        {/* The denominator travels with the claim, exactly as it does in the evidence list. */}
        {col.sharedBy} of these accounts, {col.corpusCount} in the corpus, surprise{' '}
        {col.surprise.toFixed(2)}
      </span>
    </>
  );
}

function LegendLine() {
  return (
    <>
      A filled square means that account holds that feature.{' '}
      <span className="text-accent">Blue</span> is a hard family, the operator&apos;s own acts, which
      a shared job or interest does not produce. Read down a column to see who shares one thing, and
      across a row to see what one account is tied in by.
    </>
  );
}
