import { describe, it, expect } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

/**
 * Two things a page's own metadata can silently undo, both found live.
 *
 * The root layout applies a title TEMPLATE (`%s . OMISPHERE`) and derives the canonical link and
 * the markdown alternate from the request path. A page that repeats the brand gets it twice, and a
 * page that sets `alternates` at all REPLACES the layout's whole object, dropping the markdown
 * link. Neither shows up in the browser, in TypeScript, or in a build.
 */

const appDir = join(__dirname, '..', 'app');

/** Every `page.tsx` in the app, so a route added anywhere is covered without being listed here. */
function pages(): { name: string; source: string }[] {
  const found: { name: string; source: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name === 'page.tsx' || entry.name === 'not-found.tsx') {
        found.push({ name: full.slice(appDir.length), source: readFileSync(full, 'utf8') });
      }
    }
  };
  walk(appDir);
  return found;
}

describe('page metadata', () => {
  it('finds the pages it claims to be checking', () => {
    // A walker that silently matched nothing would pass both assertions below forever.
    expect(pages().length).toBeGreaterThan(10);
  });

  it('does not repeat the brand the title template already appends', () => {
    for (const { name, source } of pages()) {
      // Both quote styles, since a dynamic title is a template literal.
      const head = source.split('export default')[0];
      const title = /title:\s*['`]([^'`]*)['`]/.exec(head);
      if (!title) continue;
      expect(title[1], `${name}: the layout template appends the brand`).not.toMatch(/OMISPHERE/i);
    }
  });

  it('leaves alternates to the layout, which derives them from the path', () => {
    for (const { name, source } of pages()) {
      const head = source.split('export default')[0];
      expect(head, `${name}: setting alternates drops the markdown link`).not.toContain('alternates:');
    }
  });

  it('checks the brand in the title, not merely anywhere in the file', () => {
    // The guard reads only the region above `export default`, so a heading in the page body that
    // legitimately names the product cannot fail it.
    const terms = pages().find((p) => p.name.includes('terms'))!;
    expect(terms.source).toContain('OMISPHERE');
  });
});
