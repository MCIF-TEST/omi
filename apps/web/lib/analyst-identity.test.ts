import { describe, expect, it } from 'vitest';
import { ANALYST_NAME, analystProviderLabel, scrubVendor } from './analyst-identity';

/**
 * The product has one analyst and it is called the Omi Analyst. The gateway it runs on is our
 * implementation detail, and naming it on the site tells a customer that what they pay for is
 * somebody else's.
 *
 * The vendor name is not in our copy anywhere; it arrives inside VALUES written by the backend and
 * rendered as data, which is why this is a render-time function rather than a review rule.
 */
describe('analystProviderLabel', () => {
  it('never returns the gateway name, whatever the provider string says', () => {
    const raw = [
      'openrouter',
      'openrouter-omi-analyst-v1',
      'openrouter->fallback:deterministic-analyst-v1',
      'OpenRouter',
      'open router',
    ];
    for (const p of raw) {
      expect(analystProviderLabel(p)).not.toMatch(/open\s*router/i);
      expect(analystProviderLabel(p)).toContain(ANALYST_NAME);
    }
  });

  it('keeps the one distinction an operator actually needs', () => {
    // Whether the model answered or the deterministic floor stood in. Losing that would make the
    // diagnostic useless, and it is expressible without naming anyone.
    expect(analystProviderLabel('openrouter-omi-analyst-v1')).toBe(`${ANALYST_NAME} (model)`);
    expect(analystProviderLabel('openrouter->fallback:deterministic-analyst-v1'))
      .toBe(`${ANALYST_NAME} (deterministic floor)`);
    expect(analystProviderLabel('deterministic-analyst-v1'))
      .toBe(`${ANALYST_NAME} (deterministic floor)`);
  });

  it('falls back to the bare name rather than rendering an empty label', () => {
    for (const p of [null, undefined, '', '   ']) {
      expect(analystProviderLabel(p)).toBe(ANALYST_NAME);
    }
  });
});

describe('scrubVendor', () => {
  it('removes the gateway name from a transport error but keeps the diagnosis', () => {
    // These strings are built by the backend and are exactly what an operator needs, apart from the
    // one word that must not be on the page.
    const out = scrubVendor('ProviderError: openrouter HTTP 404');
    expect(out).not.toMatch(/open\s*router/i);
    expect(out).toContain('404');
    expect(out).toContain('ProviderError');

    const timeout = scrubVendor('ProviderTimeout: openrouter timed out after 1 attempt(s)');
    expect(timeout).not.toMatch(/open\s*router/i);
    expect(timeout).toContain('timed out');
  });

  it('catches the spellings that actually occur', () => {
    for (const s of ['openrouter unreachable', 'OpenRouter HTTP 502', 'Open Router refused']) {
      expect(scrubVendor(s)).not.toMatch(/open\s*router/i);
    }
  });

  it('leaves an unrelated message alone', () => {
    expect(scrubVendor('ConnectionError: name resolution failed'))
      .toBe('ConnectionError: name resolution failed');
  });

  it('returns an empty string for nothing, so a caller can render a dash', () => {
    for (const s of [null, undefined, '', '  ']) expect(scrubVendor(s)).toBe('');
  });
});

// ---------------------------------------------------------------------------
// The standing rule, enforced against the source rather than remembered.
//
// The vendor name must not appear in any rendered string in the app. The one deliberate exception
// is the privacy policy, where naming a subprocessor is a legal disclosure rather than branding:
// removing it there would be a data-protection problem, not a win.
// ---------------------------------------------------------------------------
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name === '.next' || name.startsWith('.')) continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) sourceFiles(full, out);
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(full);
  }
  return out;
}

describe('the gateway is never named in the product', () => {
  it('appears in no rendered string outside the subprocessor disclosure', () => {
    const ALLOWED = [
      'app/(marketing)/privacy/page.tsx',   // subprocessor disclosure, legally required
      'lib/analyst-identity.ts',            // the module whose job is to remove it
    ];
    const offenders: string[] = [];
    for (const file of sourceFiles(process.cwd())) {
      const rel = file.slice(process.cwd().length + 1);
      if (ALLOWED.some((a) => rel === a)) continue;
      for (const [i, line] of readFileSync(file, 'utf8').split('\n').entries()) {
        // Comments explain the rule and are not rendered; a field NAME on a type is not a string.
        const code = line.replace(/\/\/.*$/, '').replace(/^\s*\*.*$/, '');
        if (/open\s*router/i.test(code) && !/openrouter_preset|openrouter_/.test(code)) {
          offenders.push(`${rel}:${i + 1}: ${line.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
