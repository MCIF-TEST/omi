import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Content has to be readable with scripting off.
 *
 * The subtlety this guards is that the markup was ALREADY complete: `Reveal` puts its children in
 * the document and hides them with `opacity-0` until an effect runs. So every text-extracting check
 * passed while a no-script visitor, and any agent driving a headless browser with JavaScript
 * disabled, saw a blank block where the free scan form is. Source-level, in the spirit of the other
 * guards in this repo, because TypeScript will not notice either half of the pair going missing.
 */

const root = join(__dirname, '..');
const read = (p: string) => readFileSync(join(root, p), 'utf8');

describe('the no-script reveal', () => {
  it('marks the hidden state with a class the stylesheet can reach', () => {
    expect(read('components/shared/reveal.tsx')).toContain('reveal-pending');
  });

  it('ships a noscript rule that overrides it', () => {
    const layout = read('app/layout.tsx');
    expect(layout).toContain('<noscript>');
    expect(layout).toContain('.reveal-pending');
    // Both properties: opacity alone would leave the element translated off its position.
    expect(layout).toMatch(/opacity:\s*1\s*!important/);
    expect(layout).toMatch(/transform:\s*none\s*!important/);
  });

  it('keeps the pair together, which is the whole failure mode', () => {
    // Either half alone is silently useless: a class nothing styles, or a rule matching nothing.
    const hasClass = read('components/shared/reveal.tsx').includes('reveal-pending');
    const hasRule = read('app/layout.tsx').includes('.reveal-pending');
    expect(hasClass).toBe(hasRule);
  });
});
