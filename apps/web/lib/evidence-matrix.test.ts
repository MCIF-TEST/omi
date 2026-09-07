/**
 * The matrix is the join the queue had been asking readers to take on faith, so what it must get
 * right is mostly about NOT overstating: three states rather than two, no derived ranking, and the
 * hard families where a reader's eye lands first.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  FAMILY_ORDER,
  HARD_FAMILIES,
  MAX_COLUMNS,
  buildEvidenceMatrix,
  isHardFamily,
  shapeOf,
} from './evidence-matrix';
import type { NetdetectEvidence } from './api';

function ev(
  family: string,
  kind: string,
  members: string[] | null | undefined,
  surprise = 4,
): NetdetectEvidence {
  return {
    family,
    kind,
    shared_by: members?.length ?? 0,
    corpus_count: 6,
    surprise,
    sentence: `${kind} shared by ${members?.length ?? 0}`,
    members,
  };
}

describe('the three states', () => {
  it('reports NOT RECORDED rather than an empty grid when no row carries its holders', () => {
    // The distinction that matters: a finding stored before holders existed is not a finding whose
    // members share nothing. Drawing an empty matrix would state the second.
    const m = buildEvidenceMatrix(['a', 'b', 'c'], [ev('identity', 'creation_week', undefined)]);
    expect(m.recorded).toBe(false);
    expect(m.rows).toEqual([]);
    expect(shapeOf(m)).toBeNull();
  });

  it('reports recorded once any row carries holders', () => {
    const m = buildEvidenceMatrix(
      ['a', 'b'],
      [ev('identity', 'creation_week', ['a', 'b']), ev('text', 'shingle', undefined)],
    );
    expect(m.recorded).toBe(true);
    // The row with no holders is dropped rather than drawn as an empty column, for the same reason.
    expect(m.columns).toHaveLength(1);
  });

  it('is not recorded when there are holders but no members to draw them against', () => {
    expect(buildEvidenceMatrix([], [ev('identity', 'k', ['a'])]).recorded).toBe(false);
  });
});

describe('the join', () => {
  it('fills a cell exactly where that member holds that feature', () => {
    const m = buildEvidenceMatrix(
      ['a', 'b', 'c'],
      [ev('identity', 'creation_week', ['a', 'b']), ev('text', 'shingle', ['b', 'c'])],
    );
    expect(m.rows.map((r) => r.cells)).toEqual([
      [true, false],
      [true, true],
      [false, true],
    ]);
  });

  it('never draws a cell for an account that is not in the member list', () => {
    // A stored row can name an account the finding no longer carries. Drawing it would put a mark
    // against a person who is not on the page.
    const m = buildEvidenceMatrix(['a'], [ev('identity', 'k', ['a', 'ghost'])]);
    expect(m.columns[0].holders.has('ghost')).toBe(false);
    expect(m.rows).toHaveLength(1);
  });

  it('keeps the finding’s own member order and never sorts by how much a row holds', () => {
    // Sorting rows by fill IS the per-member ranking `attachment.py` measured and refused, drawn
    // instead of printed. It ranked bystanders above genuine operation members.
    const m = buildEvidenceMatrix(
      ['empty', 'full'],
      [ev('identity', 'k1', ['full']), ev('network', 'k2', ['full'])],
    );
    expect(m.rows.map((r) => r.member)).toEqual(['empty', 'full']);
  });

  it('carries the weak flag from the finding and never derives it from the row', () => {
    // `weakly_attached` comes from leave-one-out set surprise. A row that merely looks sparse is
    // not the same claim, and inventing the flag here would be a second, worse membership test.
    const m = buildEvidenceMatrix(
      ['a', 'b'],
      [ev('identity', 'k', ['a', 'b'])],
      ['b'],
    );
    expect(m.rows.map((r) => r.weak)).toEqual([false, true]);
  });
});

describe('the hard families lead', () => {
  it('agrees with the API about which families are hard', () => {
    // Declared twice, in two languages, with nothing at runtime reconciling them. That is the drift
    // class this repo has paid for repeatedly, so it fails here instead of rendering the wrong
    // evidence as the discriminating half.
    const py = readFileSync(
      join(__dirname, '..', '..', 'api', 'app', 'netdetect', 'types.py'),
      'utf8',
    );
    const block = py.match(/HARD_FAMILIES:\s*frozenset\[str\]\s*=\s*frozenset\(\{([^}]*)\}\)/);
    expect(block).not.toBeNull();
    const names = [...(block as RegExpMatchArray)[1].matchAll(/FAMILY_([A-Z]+)/g)].map((x) =>
      x[1].toLowerCase(),
    );
    expect(names.sort()).toEqual([...HARD_FAMILIES].sort());
  });

  it('declares every family the API can send, so none sorts into the hard position by accident', () => {
    const py = readFileSync(
      join(__dirname, '..', '..', 'api', 'app', 'netdetect', 'types.py'),
      'utf8',
    );
    const names = [...py.matchAll(/^FAMILY_([A-Z]+) = "([a-z]+)"/gm)].map((x) => x[2]);
    expect(names.length).toBeGreaterThan(0);
    expect([...names].sort()).toEqual([...FAMILY_ORDER].sort());
  });

  it('orders the columns hard first, then by surprise inside a band', () => {
    const m = buildEvidenceMatrix(
      ['a'],
      [
        ev('timing', 'quiet_hours', ['a'], 9),
        ev('text', 'shingle', ['a'], 2),
        ev('identity', 'creation_week', ['a'], 1),
        ev('identity', 'handle_skeleton', ['a'], 5),
      ],
    );
    expect(m.columns.map((c) => c.kind)).toEqual([
      'handle_skeleton',
      'creation_week',
      'shingle',
      'quiet_hours',
    ]);
    expect(m.bands.map((b) => b.family)).toEqual(['identity', 'text', 'timing']);
    expect(m.bands[0].hard).toBe(true);
    expect(m.hardFamilyCount).toBe(1);
  });

  it('sorts an unknown family last rather than into the hard position', () => {
    const m = buildEvidenceMatrix(['a'], [ev('brandnew', 'k', ['a'], 99), ev('text', 't', ['a'], 1)]);
    expect(m.bands.map((b) => b.family)).toEqual(['text', 'brandnew']);
    expect(isHardFamily('brandnew')).toBe(false);
  });

  it('marks a member holding nothing in any hard family', () => {
    const m = buildEvidenceMatrix(
      ['carried', 'thin'],
      [ev('identity', 'k', ['carried']), ev('text', 't', ['carried', 'thin'])],
    );
    expect(m.rows.map((r) => r.noHardEvidence)).toEqual([false, true]);
  });
});

describe('the width is bounded', () => {
  it('caps the columns so a wide finding stays readable', () => {
    const many = Array.from({ length: MAX_COLUMNS + 10 }, (_, i) =>
      ev('text', `k${i}`, ['a'], MAX_COLUMNS + 10 - i),
    );
    const m = buildEvidenceMatrix(['a'], many);
    expect(m.columns).toHaveLength(MAX_COLUMNS);
    // The cap keeps the MOST surprising evidence, not the first the API happened to return.
    expect(m.columns[0].kind).toBe('k0');
  });
});

describe('the shape sentence describes and never judges', () => {
  it('names the missing hard evidence when no hard family carries anything', () => {
    const m = buildEvidenceMatrix(['a', 'b'], [ev('text', 'k', ['a', 'b'])]);
    expect(shapeOf(m)).toMatch(/only an operator produces/);
  });

  it('names how many members hold nothing in the hard families', () => {
    const m = buildEvidenceMatrix(
      ['a', 'b', 'c'],
      [ev('identity', 'k', ['a', 'b']), ev('text', 't', ['a', 'b', 'c'])],
    );
    expect(shapeOf(m)).toMatch(/1 of 3 members hold nothing in the hard families/);
  });

  it('says a solid block is equally a community, because it is', () => {
    const m = buildEvidenceMatrix(
      ['a', 'b'],
      [ev('identity', 'k', ['a', 'b']), ev('network', 'n', ['a', 'b'])],
    );
    expect(shapeOf(m)).toMatch(/equally what a tight operation and a real community look like/);
  });

  it('never states a verdict about the group', () => {
    const cases = [
      buildEvidenceMatrix(['a', 'b'], [ev('text', 'k', ['a', 'b'])]),
      buildEvidenceMatrix(['a', 'b'], [ev('identity', 'k', ['a', 'b']), ev('network', 'n', ['a', 'b'])]),
      buildEvidenceMatrix(
        ['a', 'b', 'c', 'd'],
        [ev('identity', 'k', ['a']), ev('network', 'n', ['b']), ev('text', 't', ['c'])],
      ),
    ];
    for (const m of cases) {
      const s = shapeOf(m);
      if (!s) continue;
      expect(s).not.toMatch(/\b(bot|fake|guilty|coordinated operation|is an operation)\b/i);
    }
  });
});

describe('an absent hard family is stated, not merely undrawn', () => {
  it('lists every hard family including the ones contributing nothing', () => {
    // The professional-beat control is a SOLID block with zero identity and zero network features.
    // The solidity is the alarming part and the absence is the answer, so the absence has to be
    // rendered. A band that contributes nothing draws nothing and cannot be noticed.
    const m = buildEvidenceMatrix(
      ['a', 'b'],
      [ev('text', 'shingle', ['a', 'b']), ev('timing', 'quiet', ['a', 'b'])],
    );
    expect(m.hardPresence).toEqual([
      { family: 'identity', columns: 0 },
      { family: 'network', columns: 0 },
    ]);
    expect(m.hardFamilyCount).toBe(0);
  });

  it('counts the columns a present hard family contributes', () => {
    const m = buildEvidenceMatrix(
      ['a'],
      [ev('identity', 'k1', ['a']), ev('identity', 'k2', ['a']), ev('text', 't', ['a'])],
    );
    expect(m.hardPresence).toEqual([
      { family: 'identity', columns: 2 },
      { family: 'network', columns: 0 },
    ]);
  });

  it('covers every hard family the API declares, so none can go unreported', () => {
    const m = buildEvidenceMatrix(['a'], [ev('text', 't', ['a'])]);
    expect(m.hardPresence.map((h) => h.family).sort()).toEqual([...HARD_FAMILIES].sort());
  });
});
