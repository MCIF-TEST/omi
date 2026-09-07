import { describe, expect, it } from 'vitest';
import {
  REASON_PRESETS,
  RESERVOIR_MIN_JUDGEMENTS,
  RESERVOIR_MIN_PER_CLASS,
  carryingFamilies,
  findingHeadline,
  memberLabels,
  membershipSentence,
  membershipState,
  namedCount,
  reservoirProgress,
  restsOnHardEvidence,
  runVerdict,
} from './netdetect-read';

describe('memberLabels', () => {
  it('shows the handle and keeps the id beside it', () => {
    const [l] = memberLabels(['123'], { '123': 'realname' });
    expect(l.primary).toBe('realname');
    expect(l.secondary).toBe('123');
    expect(l.named).toBe(true);
  });

  it('FALLS BACK TO THE ID rather than rendering a blank name', () => {
    // A member absent from `handles` means we have no handle for that account, NEVER that the
    // account has no handle. Rendering nothing would invent a fact about a named person; the id is
    // what we actually know. Rows recorded before handles were stored are entirely this case.
    const [l] = memberLabels(['123'], {});
    expect(l.primary).toBe('123');
    expect(l.named).toBe(false);
    expect(l.secondary).toBeNull();
  });

  it('treats a blank or whitespace handle exactly as a missing one', () => {
    const labels = memberLabels(['a', 'b'], { a: '', b: '   ' });
    expect(labels.map((l) => l.primary)).toEqual(['a', 'b']);
    expect(labels.every((l) => !l.named)).toBe(true);
  });

  it('does not repeat the id when it is already the primary', () => {
    const [l] = memberLabels(['123'], undefined);
    expect(l.secondary).toBeNull();
  });

  it('carries the weak-membership flag through without reordering anything', () => {
    const labels = memberLabels(['a', 'b', 'c'], { b: 'bee' }, ['c']);
    expect(labels.map((l) => l.id)).toEqual(['a', 'b', 'c']);
    expect(labels.map((l) => l.weak)).toEqual([false, false, true]);
  });

  it('counts how many members we can actually name', () => {
    expect(namedCount(memberLabels(['a', 'b', 'c'], { a: 'ay', c: 'see' }))).toBe(2);
  });
});

describe('carryingFamilies', () => {
  it('puts hard families first even when a soft one contributed more', () => {
    // The hard/soft split is what every publication decision in this package keys on, so ordering
    // purely by magnitude would bury the half that discriminates.
    expect(carryingFamilies({ text: 9.5, identity: 2.1 })).toEqual(['identity', 'text']);
  });

  it('orders within a class by contribution', () => {
    expect(carryingFamilies({ text: 1, timing: 5 })).toEqual(['timing', 'text']);
  });

  it('drops families that contributed nothing', () => {
    expect(carryingFamilies({ identity: 3, narrative: 0 })).toEqual(['identity']);
  });

  it('survives an empty map', () => {
    expect(carryingFamilies({})).toEqual([]);
  });
});

describe('findingHeadline', () => {
  it('describes the evidence in plain words', () => {
    const h = findingHeadline({ member_count: 8, by_family: { identity: 4, network: 3 } });
    expect(h).toContain('8 accounts');
    expect(h).toContain('how the accounts were made');
    expect(h).toContain('who and what they engage');
  });

  it('NEVER REACHES A VERDICT', () => {
    // These findings name real people who can read them, and the headline is the most screenshotted
    // line on the card. It states what was measured; it does not accuse.
    const h = findingHeadline({
      member_count: 12,
      by_family: { identity: 9, network: 8, text: 7, timing: 2 },
    }).toLowerCase();
    for (const word of ['bot', 'network of', 'operation', 'campaign', 'fake', 'inauthentic']) {
      expect(h).not.toContain(word);
    }
  });

  it('says the count rather than listing every family', () => {
    const h = findingHeadline({
      member_count: 5,
      by_family: { identity: 5, network: 4, text: 3, timing: 2, narrative: 1 },
    });
    expect(h).toContain('2 other kinds of evidence');
  });

  it('singularises a one-account finding', () => {
    expect(findingHeadline({ member_count: 1, by_family: { text: 1 } })).toContain('1 account ');
  });

  it('does not collide with itself when a finding carries more than three families', () => {
    // The one-sentence form produced "...and 2 more, more than chance in this section explains".
    // Found by reading the served page, not the source, which is the only way this class of defect
    // ever shows up.
    const h = findingHeadline({
      member_count: 23,
      by_family: { network: 5, text: 13, infrastructure: 3, timing: 2, narrative: 0.5 },
    });
    expect(h).not.toMatch(/more, more/);
    expect(h).toContain('2 other kinds of evidence');
  });

  it('singularises the overflow phrase too', () => {
    const h = findingHeadline({
      member_count: 9,
      by_family: { identity: 4, network: 3, text: 2, timing: 1 },
    });
    expect(h).toContain('1 other kind of evidence');
  });

  it('does not claim anything when no family was recorded', () => {
    const h = findingHeadline({ member_count: 4, by_family: {} });
    expect(h).toContain('not recorded');
    expect(h).not.toContain('more agreement than chance');
  });
});

describe('restsOnHardEvidence', () => {
  it('is true only for the families describing the operator own acts', () => {
    expect(restsOnHardEvidence({ identity: 3 })).toBe(true);
    expect(restsOnHardEvidence({ network: 3 })).toBe(true);
    expect(restsOnHardEvidence({ text: 9, timing: 9, narrative: 9 })).toBe(false);
  });
});

describe('membership', () => {
  const base = { attachment_checked: true, weakly_attached: [] as string[], attachment_note: null };

  it('SEPARATES "we did not look" from "everyone belongs"', () => {
    // Both present as an empty `weakly_attached` and they are opposite statements about the people
    // named. This is the same distinction as `score: null` against `0` on the analyst signals.
    expect(membershipState({ ...base, attachment_checked: false })).toBe('not-checked');
    expect(membershipState(base)).toBe('all-carry');
  });

  it('reports weak members as a third state', () => {
    expect(membershipState({ ...base, weakly_attached: ['a'] })).toBe('some-weak');
  });

  it('never says every member belongs when the test did not run', () => {
    const s = membershipSentence({ ...base, attachment_checked: false });
    expect(s).toContain('not tested');
    expect(s).not.toContain('Every account');
  });

  it('carries the abstention reason when there is one', () => {
    const s = membershipSentence({
      ...base,
      attachment_checked: false,
      attachment_note: 'too many members to test',
    });
    expect(s).toContain('too many members to test');
  });

  it('tells the reader a flagged member is still a member', () => {
    const s = membershipSentence({ ...base, weakly_attached: ['a', 'b'] });
    expect(s).toContain('still');
    expect(s).toContain('2 highlighted');
  });
});

describe('runVerdict', () => {
  const empty = {
    findings: [],
    refused: null,
    unresolvable: null,
    rejected: 0,
    corpus_size: 60,
  };

  it('reports findings when there are any', () => {
    const v = runVerdict({ ...empty, findings: [{}, {}] });
    expect(v.outcome).toBe('found');
    expect(v.title).toContain('2 findings');
  });

  it('NEVER READS A REFUSAL AS A CLEAN RESULT', () => {
    // Three of the four outcomes present as an empty findings list, and this is the one that would
    // otherwise report "nothing found" about a run that never happened.
    const v = runVerdict({ ...empty, refused: 'Too few shuffles to express that p-value.' });
    expect(v.outcome).toBe('refused');
    expect(v.detail).toContain('says nothing at all');
  });

  it('reports an unresolvable section without claiming an operation is present', () => {
    const v = runVerdict({ ...empty, unresolvable: 'One group holds 38% of this section.' });
    expect(v.outcome).toBe('unresolvable');
    expect(v.detail).toContain('not a claim that an operation is present');
  });

  it('checks refusal BEFORE domination, because a run that never happened says neither', () => {
    const v = runVerdict({ ...empty, refused: 'Corpus too small.', unresolvable: 'dominated' });
    expect(v.outcome).toBe('refused');
  });

  it('distinguishes "looked and refused" from "nothing was proposed"', () => {
    expect(runVerdict({ ...empty, rejected: 4 }).detail).toContain('4 candidates scored');
    expect(runVerdict(empty).detail).toContain('No candidate group was even proposed');
  });

  it('says a clean result is not a statement that the accounts are unrelated', () => {
    for (const rejected of [0, 3]) {
      expect(runVerdict({ ...empty, rejected }).detail).toContain('not the same as these accounts being unrelated');
    }
  });
});

describe('reservoirProgress', () => {
  it('is not ready on volume alone', () => {
    // THE BINDING CONSTRAINT IS THE WORST CLASS. Thirty dismissals and no confirmations is a
    // reservoir that can only ever teach the detector to be quieter, so the bar must not read full.
    const p = reservoirProgress({ confirmed: 0, dismissed: 30 });
    expect(p.ready).toBe(false);
    expect(p.fraction).toBe(0);
    expect(p.shortfall).toContain('8 more confirmed');
  });

  it('is ready at the documented floor', () => {
    const p = reservoirProgress({ confirmed: 15, dismissed: 15 });
    expect(p.total).toBe(RESERVOIR_MIN_JUDGEMENTS);
    expect(p.ready).toBe(true);
    expect(p.fraction).toBe(1);
    expect(p.shortfall).toBeNull();
  });

  it('is not ready when both classes are met but the total is not', () => {
    const p = reservoirProgress({ confirmed: 8, dismissed: 8 });
    expect(p.ready).toBe(false);
    expect(p.shortfall).toContain('14 more judgements');
  });

  it('tracks the worst of the three ratios', () => {
    const p = reservoirProgress({ confirmed: 4, dismissed: 20 });
    expect(p.fraction).toBeCloseTo(4 / RESERVOIR_MIN_PER_CLASS, 6);
  });

  it('stays inside 0..1 and never goes negative', () => {
    const over = reservoirProgress({ confirmed: 40, dismissed: 40 });
    expect(over.fraction).toBe(1);
    const under = reservoirProgress({ confirmed: -3, dismissed: -1 });
    expect(under.fraction).toBe(0);
    expect(under.total).toBe(0);
  });
});

describe('REASON_PRESETS', () => {
  it('carries both verdicts, because a reservoir of one class fits nothing', () => {
    expect(REASON_PRESETS.some((p) => p.verdict === 'confirm')).toBe(true);
    expect(REASON_PRESETS.some((p) => p.verdict === 'dismiss')).toBe(true);
  });

  it('states a reason rather than a label, since the reason is what gets fitted against', () => {
    for (const p of REASON_PRESETS) {
      expect(p.text.trim().length).toBeGreaterThan(40);
      expect(p.text.trim()).not.toBe(p.label);
    }
  });

  it('has the confirm presets claim a hand check', () => {
    // A confirmation is the rarer and more valuable label, and it should never be reachable by
    // agreeing with the detector: the preset text says the operator looked.
    for (const p of REASON_PRESETS.filter((x) => x.verdict === 'confirm')) {
      expect(p.text.toLowerCase()).toContain('checked by hand');
    }
  });

  it('keeps every label short enough to sit on a chip', () => {
    for (const p of REASON_PRESETS) expect(p.label.length).toBeLessThanOrEqual(24);
  });
});
