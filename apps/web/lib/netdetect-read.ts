/**
 * Turning a finding into something an operator can read at a glance.
 *
 * The queue was built to be CORRECT before it was built to be read, and it shows: a finding
 * rendered as a wrap of raw platform ids, four unlabelled numbers, and a truncated list of evidence
 * sentences. Every one of those is accurate. None of them answers the question somebody opening the
 * page actually has, which is "what is this claiming, and do I believe it".
 *
 * Everything here is PURE and every rule in it is a claim about named real people, which is why it
 * is a module with tests rather than expressions inlined into JSX. The rules that matter:
 *
 *   - a missing handle falls back to the id, and never renders as a blank name;
 *   - a plain-English headline states the SHAPE of the evidence, never a verdict;
 *   - "we did not look" never renders as "we looked and found nothing".
 */

import { FAMILY_MEANING, FAMILY_ORDER, isHardFamily } from './evidence-matrix';

// Deliberately NOT importing `NetdetectFinding`: every function here takes the structural subset it
// actually reads. That keeps each rule testable from a two-field literal rather than from a
// thirty-field fixture, and a test that has to build the whole row to check one sentence is a test
// nobody writes.

/**
 * How to show one member.
 *
 * THE FALLBACK IS THE WHOLE POINT. `handles` is partial: it is written at detection time and rows
 * recorded before that carry none, so an absent key means "we have no handle for this account" and
 * NOT "this account has no handle". Rendering a blank there would invent a fact about a named
 * person; rendering the id is the honest thing, because the id is what we actually know.
 */
export interface MemberLabel {
  id: string;
  /** What to show. The handle when we have one, otherwise the id itself. */
  primary: string;
  /** The id, when it is not already the primary. Null when showing it twice would be noise. */
  secondary: string | null;
  /** Whether a real handle backed this label, so a caller can style the two cases apart. */
  named: boolean;
  /** Flagged by the leave-one-out membership test as not carrying the finding. */
  weak: boolean;
}

export function memberLabels(
  members: string[],
  handles: Record<string, string> | undefined,
  weaklyAttached: string[] = [],
): MemberLabel[] {
  const weak = new Set(weaklyAttached);
  return members.map((id) => {
    const raw = handles?.[id];
    const handle = typeof raw === 'string' ? raw.trim() : '';
    return {
      id,
      primary: handle || id,
      secondary: handle ? id : null,
      named: Boolean(handle),
      weak: weak.has(id),
    };
  });
}

/** How many of a finding's members we can put a name to, for an honest "3 of 8 named" line. */
export function namedCount(labels: MemberLabel[]): number {
  return labels.filter((l) => l.named).length;
}

/**
 * The families a finding actually rests on, strongest first, hard families ahead of soft ones.
 *
 * `by_family` carries a weighted log10 contribution per family. Ordering by that alone would let a
 * large soft contribution outrank a hard one, and the hard/soft split is the thing every
 * publication decision in this package keys on, so hard families sort first regardless of size.
 */
export function carryingFamilies(byFamily: Record<string, number>): string[] {
  const present = Object.entries(byFamily ?? {})
    .filter(([, v]) => typeof v === 'number' && v > 0)
    .sort((a, b) => {
      const hard = Number(isHardFamily(b[0])) - Number(isHardFamily(a[0]));
      if (hard !== 0) return hard;
      if (b[1] !== a[1]) return b[1] - a[1];
      // FAMILY_ORDER is a const tuple, so its indexOf is narrowed to the known family names. A
      // family the server adds later is not in it and must still sort deterministically rather
      // than throwing, so the lookup is widened and an unknown one sorts last.
      const order = FAMILY_ORDER as readonly string[];
      const ia = order.indexOf(a[0]);
      const ib = order.indexOf(b[0]);
      return (ia === -1 ? order.length : ia) - (ib === -1 ? order.length : ib);
    });
  return present.map(([k]) => k);
}

/**
 * One sentence saying what the finding claims, in words rather than statistics.
 *
 * IT DESCRIBES THE EVIDENCE, IT DOES NOT REACH A VERDICT. "These eight accounts share how they were
 * made and who they engage" is a statement about what was measured. "These eight accounts are a bot
 * network" is an accusation the evidence cannot carry, and this product publishes about real people
 * who can read it. The headline never says operation, network, bot, or campaign for that reason.
 */
export function findingHeadline(finding: {
  member_count: number;
  by_family: Record<string, number>;
}): string {
  const families = carryingFamilies(finding.by_family);
  const n = finding.member_count;
  const accounts = `${n} account${n === 1 ? '' : 's'}`;

  if (families.length === 0) {
    // Should not happen for a stored finding, but an empty by_family must not render as a
    // confident claim about nothing.
    return `${accounts} grouped on evidence that was not recorded by family.`;
  }

  const phrases = families.slice(0, 3).map((f) => FAMILY_MEANING[f] ?? f);
  const listed =
    phrases.length === 1
      ? phrases[0]
      : `${phrases.slice(0, -1).join(', ')} and ${phrases[phrases.length - 1]}`;
  // Two sentences rather than one. The single-sentence form collided with itself the moment a
  // finding carried more than three families: "...and 2 more, more than chance in this section
  // explains". Caught by reading the rendered page rather than the source.
  const more =
    families.length > 3 ? `, and ${families.length - 3} other kind${families.length - 3 === 1 ? '' : 's'} of evidence` : '';

  return `${accounts} share ${listed}${more}. That is more agreement than chance in this section explains.`;
}

/**
 * Whether the finding rests on evidence in a hard family, which is what separates an operation from
 * a group of people who genuinely have things in common.
 *
 * Measured and recorded in CLAUDE.md: total accumulated agreement does NOT tell an operation from a
 * newsroom, because reporters on one beat genuinely keep appearing together. Only evidence in the
 * families that describe the operator's own acts does.
 */
export function restsOnHardEvidence(byFamily: Record<string, number>): boolean {
  return carryingFamilies(byFamily).some(isHardFamily);
}

/** The three membership states, which an empty `weakly_attached` cannot distinguish on its own. */
export type MembershipState = 'not-checked' | 'all-carry' | 'some-weak';

export function membershipState(finding: {
  attachment_checked: boolean;
  weakly_attached: string[];
}): MembershipState {
  if (!finding.attachment_checked) return 'not-checked';
  return finding.weakly_attached.length > 0 ? 'some-weak' : 'all-carry';
}

/**
 * What the membership test says, in a sentence.
 *
 * THREE STATES AND THE MIDDLE ONE IS EASY TO LOSE. "Membership was not tested" and "every member
 * carries this finding" both present as an empty list and are opposite statements about the people
 * named, so this never leaves the difference to inference.
 */
export function membershipSentence(finding: {
  attachment_checked: boolean;
  weakly_attached: string[];
  attachment_note: string | null;
}): string {
  switch (membershipState(finding)) {
    case 'not-checked':
      return finding.attachment_note
        ? `Membership was not tested: ${finding.attachment_note}`
        : 'Membership was not tested, so this is not a statement that every account below belongs.';
    case 'some-weak': {
      const n = finding.weakly_attached.length;
      return `${n} highlighted account${n === 1 ? '' : 's'} did not carry this finding. ${
        n === 1 ? 'It is' : 'They are'
      } still ${n === 1 ? 'a member' : 'members'}; check ${
        n === 1 ? 'that name' : 'those names'
      } against the evidence first.`;
    }
    default:
      return 'Every account below carries this finding.';
  }
}

/** The four outcomes of a run, three of which present as an empty findings list. */
export type RunOutcome = 'found' | 'refused' | 'unresolvable' | 'clean';

export interface RunVerdict {
  outcome: RunOutcome;
  /** The headline, in the operator's language rather than the detector's. */
  title: string;
  /** What it means, and specifically what it does NOT mean. */
  detail: string;
}

/**
 * Classify a run.
 *
 * AN EMPTY FINDINGS LIST IS NOT A CLEAN RESULT, and this is the function that stops it reading as
 * one. `refused` means the run could not be performed; `unresolvable` means one group is large
 * enough in this section to poison the null, so the section cannot resolve itself in EITHER
 * direction; only the fourth case is "we looked at candidates and refused all of them".
 *
 * Order matters: `refused` is checked before `unresolvable`, because a run that never happened has
 * nothing to say about domination either.
 */
export function runVerdict(run: {
  findings: unknown[];
  refused: string | null;
  unresolvable: string | null;
  rejected: number;
  corpus_size: number;
}): RunVerdict {
  if (run.refused) {
    return {
      outcome: 'refused',
      title: 'The detector could not run here',
      detail: `${run.refused} Nothing was tested, so this says nothing at all about these accounts.`,
    };
  }
  if (run.unresolvable) {
    return {
      outcome: 'unresolvable',
      title: 'This section cannot resolve itself',
      detail: `${run.unresolvable} The same statistic fires on a fan community filling a small section, so this is not a claim that an operation is present. Sweep it against the known operations instead.`,
    };
  }
  if (run.findings.length > 0) {
    const n = run.findings.length;
    return {
      outcome: 'found',
      title: `${n} finding${n === 1 ? '' : 's'} to review`,
      detail: `Out of ${run.corpus_size} accounts. Each one is a lead: judging it is what records ground truth, and nothing here reaches a customer.`,
    };
  }
  return {
    outcome: 'clean',
    title: 'Nothing cleared the correction',
    detail:
      run.rejected > 0
        ? `${run.rejected} candidate${run.rejected === 1 ? '' : 's'} scored and none beat the shuffled search. That is a real answer: no mechanical tell was found, which is not the same as these accounts being unrelated.`
        : 'No candidate group was even proposed. No mechanical tell was found, which is not the same as these accounts being unrelated.',
  };
}

/**
 * Progress toward a reservoir the calibration report will fit against.
 *
 * The report refuses to recommend anything below 30 judgements with at least 8 of each class, and
 * nothing produces those automatically: they arrive one operator click at a time. A sentence saying
 * "29 more judgements" is a fact nobody can pace themselves against; a fraction is.
 *
 * BOTH CLASSES ARE REQUIRED and the overall count is not enough on its own, which is why this
 * reports the binding shortfall rather than a single percentage. Thirty dismissals and no
 * confirmations can only ever teach the detector to be quieter.
 */
export const RESERVOIR_MIN_JUDGEMENTS = 30;
export const RESERVOIR_MIN_PER_CLASS = 8;

export interface ReservoirProgress {
  confirmed: number;
  dismissed: number;
  total: number;
  /** 0..1 over the binding constraint, so the bar cannot read full while a class is short. */
  fraction: number;
  ready: boolean;
  /** What is still missing, or null when the reservoir is deep enough. */
  shortfall: string | null;
}

export function reservoirProgress(counts: {
  confirmed: number;
  dismissed: number;
}): ReservoirProgress {
  const confirmed = Math.max(0, counts.confirmed);
  const dismissed = Math.max(0, counts.dismissed);
  const total = confirmed + dismissed;

  const needTotal = Math.max(0, RESERVOIR_MIN_JUDGEMENTS - total);
  const needConfirmed = Math.max(0, RESERVOIR_MIN_PER_CLASS - confirmed);
  const needDismissed = Math.max(0, RESERVOIR_MIN_PER_CLASS - dismissed);
  const ready = needTotal === 0 && needConfirmed === 0 && needDismissed === 0;

  // The bar tracks the WORST of the three ratios, so it cannot sit near full on 29 dismissals and
  // no confirmations, which is the state that teaches the detector the least.
  const fraction = ready
    ? 1
    : Math.min(
        total / RESERVOIR_MIN_JUDGEMENTS,
        confirmed / RESERVOIR_MIN_PER_CLASS,
        dismissed / RESERVOIR_MIN_PER_CLASS,
      );

  const parts: string[] = [];
  if (needTotal > 0) parts.push(`${needTotal} more judgement${needTotal === 1 ? '' : 's'}`);
  if (needConfirmed > 0) parts.push(`${needConfirmed} more confirmed`);
  if (needDismissed > 0) parts.push(`${needDismissed} more dismissed`);

  return {
    confirmed,
    dismissed,
    total,
    fraction: Math.max(0, Math.min(1, fraction)),
    ready,
    shortfall: parts.length > 0 ? parts.join(', ') : null,
  };
}

/**
 * The recurring verdicts, as one-click starting points for the required reason.
 *
 * JUDGING IS THE BOTTLENECK. Thirty judgements is the whole cost of calibrating this detector and
 * they arrive one at a time, so the reason box being a blank rectangle is a real tax. Every preset
 * here is a shape the precision suite already treats as a control, which is why they are these and
 * not a generic list.
 *
 * THEY FILL AN EDITABLE BOX AND NEVER SUBMIT ON THEIR OWN. A preset that judged in one click would
 * make it possible to record a verdict about named people without reading the finding, and the
 * reason is the only thing a later calibration can be fitted against: a queue of identical canned
 * strings is worth about as much as no reason at all.
 */
export interface ReasonPreset {
  verdict: 'confirm' | 'dismiss';
  label: string;
  text: string;
}

export const REASON_PRESETS: ReasonPreset[] = [
  {
    verdict: 'dismiss',
    label: 'One beat',
    text: 'Professionals covering one beat. They share a topic, a working day and a publishing tool because the job produces those, not because anyone coordinated them.',
  },
  {
    verdict: 'dismiss',
    label: 'Fan community',
    text: 'A fan community. They talk to each other and converge on the same accounts because that is what a community does.',
  },
  {
    verdict: 'dismiss',
    label: 'Same platform template',
    text: 'The shared text is platform-generated boilerplate rather than anything these accounts wrote.',
  },
  {
    verdict: 'dismiss',
    label: 'Swept-in bystanders',
    text: 'The core looks real but too much of the named membership is ordinary accounts caught by the community detection.',
  },
  {
    verdict: 'confirm',
    label: 'Same script',
    text: 'Checked by hand: near-identical text posted by several of these accounts under unrelated posts.',
  },
  {
    verdict: 'confirm',
    label: 'Provisioned together',
    text: 'Checked by hand: the accounts were created in the same narrow window and share publishing infrastructure.',
  },
];
