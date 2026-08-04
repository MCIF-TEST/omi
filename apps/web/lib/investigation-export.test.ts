import { describe, it, expect } from 'vitest';
import {
  buildExportRows,
  exportColumns,
  exportFilename,
  scannedAccountsFrom,
  toCsv,
  toTsv,
  type ScannedAccount,
} from './investigation-export';
import type { CommenterAssessment } from './api';

const NOW = Date.parse('2026-01-01T00:00:00Z');

function account(over: Partial<ScannedAccount> = {}): ScannedAccount {
  return {
    handle: 'alice',
    external_id: 'x1',
    tier: 'low',
    probability: 0.12,
    intent_label: null,
    ...over,
  };
}

function read(over: Partial<CommenterAssessment> = {}): CommenterAssessment {
  return {
    ref: 'A1',
    external_id: 'x1',
    handle: 'alice',
    omi_score: 20,
    suspicion_tier: 'low',
    assessment: 'Reads like a real person.',
    citations: ['A1'],
    resolved: true,
    ...over,
  };
}

describe('scannedAccountsFrom', () => {
  it('returns an empty list rather than throwing on anything unexpected', () => {
    expect(scannedAccountsFrom(undefined)).toEqual([]);
    expect(scannedAccountsFrom(null)).toEqual([]);
    expect(scannedAccountsFrom({})).toEqual([]);
    expect(scannedAccountsFrom({ video: null })).toEqual([]);
    expect(scannedAccountsFrom({ video: { commenters: 'nope' } })).toEqual([]);
    expect(scannedAccountsFrom({ video: { commenters: [null, 7, {}] } })).toEqual([]);
  });

  it('prefers the coordination-adjusted probability, which is the number the product shows', () => {
    const [row] = scannedAccountsFrom({
      video: {
        commenters: [
          {
            external_id: 'x1', handle: 'a', tier: 'high',
            overall_probability: 0.4, coordination_adjusted_probability: 0.9,
          },
        ],
      },
    });
    expect(row.probability).toBe(0.9);
  });

  it('falls back to the raw probability when no adjustment was made', () => {
    const [row] = scannedAccountsFrom({
      video: { commenters: [{ external_id: 'x1', overall_probability: 0.4 }] },
    });
    expect(row.probability).toBe(0.4);
  });
});

describe('buildExportRows', () => {
  it('keeps accounts the analyst never reached, with an empty score', () => {
    // The whole point of exporting the engine list rather than the analyst's: a batched run can
    // finish having skipped accounts the customer paid a credit to scan. Dropping them would make
    // the file quietly smaller than the investigation.
    const rows = buildExportRows(
      [account({ external_id: 'x1' }), account({ external_id: 'x2', handle: 'bob', tier: 'high', probability: 0.8 })],
      [read({ external_id: 'x1' })],
      NOW,
    );
    expect(rows).toHaveLength(2);
    const bob = rows.find((r) => r.account_id === 'x2')!;
    expect(bob.omi_score).toBeNull();
    expect(bob.engine_tier).toBe('high');
    expect(bob.engine_score).toBe(80);
    expect(bob.assessment).toBe('');
  });

  it('joins on external_id, not the handle', () => {
    const rows = buildExportRows(
      [account({ external_id: 'x1', handle: 'alice' })],
      [read({ external_id: 'x1', handle: 'alice_renamed', omi_score: 71 })],
      NOW,
    );
    expect(rows[0].omi_score).toBe(71);
    // Identity comes from the scan, which is what the engine row was built from.
    expect(rows[0].handle).toBe('alice');
  });

  it('ignores an unresolved read, which names no account', () => {
    const rows = buildExportRows(
      [account({ external_id: 'x1' })],
      [read({ external_id: 'x1', resolved: false, omi_score: 90 })],
      NOW,
    );
    expect(rows[0].omi_score).toBeNull();
  });

  it('still exports a read whose account is missing from the engine list', () => {
    const rows = buildExportRows([], [read({ external_id: 'ghost', omi_score: 55 })], NOW);
    expect(rows).toHaveLength(1);
    expect(rows[0].account_id).toBe('ghost');
    expect(rows[0].omi_score).toBe(55);
  });

  it('sorts worst first, falling back to the engine score where there is no analyst one', () => {
    const rows = buildExportRows(
      [
        account({ external_id: 'a', probability: 0.9 }),
        account({ external_id: 'b', probability: 0.1 }),
        account({ external_id: 'c', probability: 0.5 }),
      ],
      [read({ external_id: 'b', omi_score: 95 })],
      NOW,
    );
    expect(rows.map((r) => r.account_id)).toEqual(['b', 'a', 'c']);
  });

  it('clamps and rounds a score the model got wrong', () => {
    const rows = buildExportRows(
      [account({ external_id: 'x1' })],
      [read({ omi_score: 900 })],
      NOW,
    );
    expect(rows[0].omi_score).toBe(100);
    expect(buildExportRows([account()], [read({ omi_score: 42.7 })], NOW)[0].omi_score).toBe(43);
  });

  it('computes account age from the creation date and carries the date too', () => {
    const rows = buildExportRows(
      [account()],
      [read({ account_created_at: '2025-12-02T00:00:00Z' })],
      NOW,
    );
    expect(rows[0].account_age_days).toBe(30);
    // The ISO date is exported as well: an age computed at export time goes stale in a saved file.
    expect(rows[0].account_created).toBe('2025-12-02T00:00:00Z');
  });

  it('leaves a missing metadata field empty rather than calling it zero', () => {
    // null means the platform never told us; 0 would be a claim about the account.
    const rows = buildExportRows([account()], [read()], NOW);
    expect(rows[0].followers).toBeNull();
    expect(rows[0].following).toBeNull();
    expect(rows[0].posts).toBeNull();
    expect(rows[0].account_age_days).toBeNull();
  });

  it('materialises all eight signals, preserving a null score', () => {
    const rows = buildExportRows(
      [account()],
      [read({
        signals: [
          { name: 'temporal', score: 40, reason: null },
          { name: 'voice', score: null, reason: 'No history was collected.' },
        ],
      })],
      NOW,
    );
    expect(Object.keys(rows[0].signals!)).toHaveLength(8);
    expect(rows[0].signals!.temporal).toBe(40);
    // A dimension the model could not read stays null. Zero would mean "looks like a real person",
    // which is the opposite of "we could not tell".
    expect(rows[0].signals!.voice).toBeNull();
    expect(rows[0].signals!.profile).toBeNull();
  });
});

describe('exportColumns', () => {
  it('omits the admin-only columns when the served rows do not carry them', () => {
    const rows = buildExportRows([account()], [read()], NOW);
    const keys = exportColumns(rows).map((c) => c.key);
    expect(keys).not.toContain('confidence');
    expect(keys.some((k) => k.startsWith('signal_'))).toBe(false);
    expect(keys[keys.length - 1]).toBe('assessment');
  });

  it('includes them when the data has them, which is the viewer gate deciding, not this file', () => {
    const rows = buildExportRows(
      [account()],
      [read({ confidence: 60, signals: [{ name: 'temporal', score: 40, reason: null }] })],
      NOW,
    );
    const keys = exportColumns(rows).map((c) => c.key);
    expect(keys).toContain('confidence');
    expect(keys).toContain('signal_temporal');
    expect(keys).toContain('signal_history_authenticity');
    expect(keys[keys.length - 1]).toBe('assessment');
  });
});

describe('toCsv', () => {
  const rows = buildExportRows([account()], [read()], NOW);

  it('puts the header on the first row', () => {
    const body = toCsv(rows).replace(/^﻿/, '');
    expect(body.split('\r\n')[0]).toBe(
      'handle,account_id,omi_score,tier,engine_tier,engine_score,followers,following,'
      + 'account_created,account_age_days,posts,intent,assessment',
    );
  });

  it('starts with a byte order mark so Excel reads it as UTF-8', () => {
    // Without this, Excel on Windows decodes the file as the local codepage and mangles every
    // non-Latin handle, which this data has plenty of.
    expect(toCsv(rows).charCodeAt(0)).toBe(0xfeff);
  });

  it('quotes a field containing a comma, a quote or a newline', () => {
    const tricky = buildExportRows(
      [account({ handle: 'a,b' })],
      [read({ assessment: 'It said "buy my course".\nTwice.' })],
      NOW,
    );
    const csv = toCsv(tricky);
    expect(csv).toContain('"a,b"');
    expect(csv).toContain('"It said ""buy my course"".\nTwice."');
  });

  it('carries the scope statement after the data, never before the header', () => {
    const lines = toCsv(rows).replace(/^﻿/, '').split('\r\n');
    expect(lines[0].startsWith('handle,')).toBe(true);
    const footer = lines.filter((l) => l.startsWith('# ') || l.startsWith('"# '));
    expect(footer.length).toBeGreaterThan(0);
    expect(toCsv(rows)).toContain('probabilistic readings of public behaviour');
    expect(toCsv(rows)).toContain('/accuracy');
  });
});

describe('toTsv', () => {
  it('flattens whitespace so a pasted verdict cannot split into extra cells or rows', () => {
    const rows = buildExportRows(
      [account()],
      [read({ assessment: 'Line one.\nLine\ttwo.' })],
      NOW,
    );
    const lines = toTsv(rows).split('\n');
    expect(lines).toHaveLength(2);
    expect(lines[1].split('\t')).toHaveLength(exportColumns(rows).length);
    expect(lines[1]).toContain('Line one. Line two.');
  });

  it('carries no scope footer: the clipboard target is a spreadsheet, not a document', () => {
    const rows = buildExportRows([account()], [read()], NOW);
    expect(toTsv(rows)).not.toContain('probabilistic readings');
  });
});

describe('exportFilename', () => {
  it('names the investigation and the day it was scanned', () => {
    expect(exportFilename('bad-actors-42', '2026-01-01T10:00:00Z'))
      .toBe('omisphere-bad-actors-42-2026-01-01-accounts.csv');
  });

  it('strips the path separators out of a slug, so the name can never traverse', () => {
    expect(exportFilename('../../etc/passwd')).toBe('omisphere-..-..-etc-passwd-accounts.csv');
  });

  it('survives a missing or unparseable date', () => {
    expect(exportFilename('s')).toBe('omisphere-s-accounts.csv');
    expect(exportFilename('s', 'not-a-date')).toBe('omisphere-s-accounts.csv');
  });
});
