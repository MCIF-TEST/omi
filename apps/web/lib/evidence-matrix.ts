/**
 * The finding, as the incidence structure it actually is.
 *
 * A netdetect finding is a claim about WHICH named accounts share WHICH rare behaviours. The queue
 * had been rendering that as two disconnected projections of it: a flat row of member chips, and a
 * flat list of evidence sentences carrying only a count. Nothing on the page joined them, so the
 * question a reviewer actually has about a group of named real people, "are these the same people
 * throughout, or two sub-groups joined at a seam", could only be taken on faith.
 *
 * This builds the join: members down the side, the finding's own evidence features across the top,
 * grouped into family bands. Three things that are currently prose or invisible become shape:
 *
 *  - THE GATES. `MIN_FAMILIES` is how many bands have any fill; `MAX_SINGLE_FAMILY_SHARE` is one
 *    band being vastly wider than the rest; `MIN_HARD_EVIDENCE` is whether the hard bands have
 *    anything in them at all. Those three decide whether a finding is publishable and they are
 *    currently only ever stated as a sentence after the fact.
 *  - THE SHAPE. A solid block is everyone doing the same things. A ragged corner is a sub-group.
 *  - THE BYSTANDER. A swept-in account is a row that is empty across the hard bands.
 *
 * WHY THIS IS ALLOWED WHERE A PER-MEMBER NUMBER WAS NOT. `attachment.py` measured the obvious score
 * (how much shared evidence a member participates in) and refused to publish it, because it ranks
 * some bystanders ABOVE genuine operation members. A matrix shows COMPOSITION rather than
 * magnitude: it says which KIND of evidence each member holds, and the kind is what discriminates.
 * That is the same distinction corroboration draws between `log_lr`, which does not separate an
 * operation from a newsroom, and `hard_pairs`, which does. So the columns are ordered by family
 * with the hard families first, and no row ever carries a count or a rank.
 */

import type { NetdetectEvidence } from '@/lib/api';

/**
 * Families where innocent sharing is genuinely implausible: the operator's OWN acts. Mirrors
 * `HARD_FAMILIES` in `app/netdetect/types.py`, and `evidence-matrix.test.ts` fails if the two
 * drift, because two copies of this in two languages with nothing reconciling them is the exact
 * class of bug this repo has paid for before.
 */
export const HARD_FAMILIES = ['identity', 'network'] as const;

/**
 * Column order. Hard families first so the discriminating evidence is what a reader's eye lands on,
 * then the rest by how implausible innocent sharing is, which is the order of `FAMILY_WEIGHT`.
 */
export const FAMILY_ORDER = [
  'identity',
  'network',
  'infrastructure',
  'narrative',
  'text',
  'timing',
] as const;

/** One-line reading of what a family means, for the band header. */
export const FAMILY_MEANING: Record<string, string> = {
  identity: 'how the accounts were made',
  network: 'who and what they engage',
  infrastructure: 'what they publish with',
  narrative: 'what they name and tag',
  text: 'what they wrote',
  timing: 'when they act',
};

export function isHardFamily(family: string): boolean {
  return (HARD_FAMILIES as readonly string[]).includes(family);
}

export interface MatrixColumn {
  /** Position in the flattened column list, so a cell can find its row bit without a lookup. */
  index: number;
  family: string;
  hard: boolean;
  kind: string;
  /** Members holding this feature, as a set for O(1) cell lookup. */
  holders: Set<string>;
  surprise: number;
  sharedBy: number;
  corpusCount: number;
  sentence: string;
}

export interface MatrixBand {
  family: string;
  hard: boolean;
  columns: MatrixColumn[];
}

export interface MatrixRow {
  member: string;
  /** From the finding's own `weakly_attached`. NEVER derived from this row's own fill. */
  weak: boolean;
  /** Column index -> held. Parallel to the flattened column list. */
  cells: boolean[];
  /** True when this member holds nothing in any hard family. */
  noHardEvidence: boolean;
}

export interface EvidenceMatrix {
  bands: MatrixBand[];
  columns: MatrixColumn[];
  rows: MatrixRow[];
  /** How many distinct families carry any evidence here. The `MIN_FAMILIES` gate, made visible. */
  familyCount: number;
  hardFamilyCount: number;
  /**
   * Every hard family and how many features it contributes, INCLUDING the ones contributing none.
   *
   * A reader cannot notice a band that is not drawn, and "no evidence in the families only an
   * operator produces" is the whole verdict on the professional-beat control: measured, that
   * finding is a solid, alarming-looking block with zero identity and zero network columns. An
   * absence has to be stated to be read, the same reason `phase_of` treats dormancy as an event
   * and `attachment_checked` is explicit.
   */
  hardPresence: { family: string; columns: number }[];
  /**
   * Null when no evidence row recorded its holders, which is NOT the same as an empty matrix.
   * Callers must branch on this rather than on `rows` being empty, the same rule
   * `attachment_checked` follows.
   */
  recorded: boolean;
}

/**
 * Cheap predicate for callers that must choose a LAYOUT before paying to build the matrix.
 *
 * Exported so the queue can render one member list rather than two: the matrix's row labels are
 * the member list when holders were recorded, and a chip row only when they were not.
 */
export function hasHolderData(evidence: NetdetectEvidence[]): boolean {
  return evidence.some((e) => Array.isArray(e.members) && e.members.length > 0);
}

/** Cap the drawn columns. A grid wider than this stops being readable and starts being wallpaper. */
export const MAX_COLUMNS = 28;

/**
 * Build the matrix.
 *
 * Rows keep the finding's own member order and are NEVER sorted by how much they hold: that would
 * be the refused per-member ranking, drawn instead of printed.
 */
export function buildEvidenceMatrix(
  members: string[],
  evidence: NetdetectEvidence[],
  weaklyAttached: string[] = [],
): EvidenceMatrix {
  const withHolders = evidence.filter((e) => Array.isArray(e.members) && e.members.length > 0);
  if (members.length === 0 || withHolders.length === 0) {
    return {
      bands: [], columns: [], rows: [], familyCount: 0, hardFamilyCount: 0,
      hardPresence: [], recorded: false,
    };
  }

  const memberSet = new Set(members);
  const ranked = [...withHolders].sort((a, b) => {
    const fa = FAMILY_ORDER.indexOf(a.family as (typeof FAMILY_ORDER)[number]);
    const fb = FAMILY_ORDER.indexOf(b.family as (typeof FAMILY_ORDER)[number]);
    // An unknown family sorts last rather than first: a family added to the API and not yet to
    // FAMILY_ORDER must not silently take the position the hard evidence is read in.
    const oa = fa === -1 ? FAMILY_ORDER.length : fa;
    const ob = fb === -1 ? FAMILY_ORDER.length : fb;
    if (oa !== ob) return oa - ob;
    return b.surprise - a.surprise;
  });

  const columns: MatrixColumn[] = ranked.slice(0, MAX_COLUMNS).map((e, index) => ({
    index,
    family: e.family,
    hard: isHardFamily(e.family),
    kind: e.kind,
    // Intersected with the finding's members, so a stale stored row naming an account that is no
    // longer in the group cannot draw a cell against a member who is not on the page.
    holders: new Set((e.members ?? []).filter((m) => memberSet.has(m))),
    surprise: e.surprise,
    sharedBy: e.shared_by,
    corpusCount: e.corpus_count,
    sentence: e.sentence,
  }));

  const bands: MatrixBand[] = [];
  for (const col of columns) {
    const last = bands[bands.length - 1];
    if (last && last.family === col.family) last.columns.push(col);
    else bands.push({ family: col.family, hard: col.hard, columns: [col] });
  }

  const weak = new Set(weaklyAttached);
  const rows: MatrixRow[] = members.map((member) => {
    const cells = columns.map((c) => c.holders.has(member));
    return {
      member,
      weak: weak.has(member),
      cells,
      noHardEvidence: !columns.some((c, i) => c.hard && cells[i]),
    };
  });

  return {
    bands,
    columns,
    rows,
    familyCount: bands.length,
    hardFamilyCount: bands.filter((b) => b.hard).length,
    hardPresence: HARD_FAMILIES.map((family) => ({
      family,
      columns: columns.filter((c) => c.family === family).length,
    })),
    recorded: true,
  };
}

/**
 * One sentence naming the shape, for readers who will not read a grid.
 *
 * Deliberately descriptive and never a verdict: it says what the evidence looks like, not what the
 * group is. The detector's own refusals are the thing that decides publishability, and they are
 * already stated on the card.
 */
export function shapeOf(matrix: EvidenceMatrix): string | null {
  if (!matrix.recorded || matrix.rows.length === 0) return null;

  const total = matrix.rows.length * matrix.columns.length;
  if (total === 0) return null;
  const filled = matrix.rows.reduce((n, r) => n + r.cells.filter(Boolean).length, 0);
  const density = filled / total;
  const noHard = matrix.rows.filter((r) => r.noHardEvidence).length;

  if (matrix.hardFamilyCount === 0) {
    return 'Nothing here is in the families only an operator produces. Whatever these accounts share, a shared job or a shared interest also produces it.';
  }
  if (noHard > 0) {
    return `${noHard} of ${matrix.rows.length} members hold nothing in the hard families. The evidence tying them in is the kind a profession or a fandom also produces.`;
  }
  if (density >= 0.75) {
    return 'Every member holds most of the evidence. A block this solid is a group doing one thing together, which is equally what a tight operation and a real community look like.';
  }
  if (density <= 0.35) {
    return 'The evidence is sparse and unevenly held. Read down the columns before the rows: this may be sub-groups sharing different things rather than one group sharing everything.';
  }
  return null;
}
