import { describe, it, expect } from 'vitest';

import {
  AGENT_PAGES,
  AGENT_PAGE_BY_PATH,
  AGENT_PAGE_BY_MARKDOWN_PATH,
  indexablePaths,
  llmsTxt,
  markdownPath,
} from './agent-content';

/**
 * This module is the single source for four machine-only surfaces: the sitemap, the negotiated
 * markdown, llms.txt and the 404 recovery list. Nothing at runtime reconciles them and no human
 * ever looks at any of them, so drift here is silent by construction. These tests are the
 * reconciliation.
 */

const BASE = 'https://omisphere.online';

describe('the page set', () => {
  it('has no duplicate paths, which would silently drop a page from the lookup', () => {
    const paths = AGENT_PAGES.map((p) => p.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('gives every page a title, a one-line summary and a body', () => {
    for (const page of AGENT_PAGES) {
      expect(page.title.trim().length, page.path).toBeGreaterThan(0);
      expect(page.summary.trim().length, page.path).toBeGreaterThan(0);
      expect(page.markdown.trim().length, page.path).toBeGreaterThan(80);
    }
  });

  it('starts every body with an H1, which is what a markdown reader keys on', () => {
    for (const page of AGENT_PAGES) {
      expect(page.markdown.trimStart().startsWith('# '), page.path).toBe(true);
    }
  });

  it('carries no em or en dash, the house rule that also binds generated prose', () => {
    for (const page of AGENT_PAGES) {
      expect(page.markdown, page.path).not.toMatch(/[–—]/);
      expect(page.summary, page.path).not.toMatch(/[–—]/);
    }
    expect(llmsTxt(BASE)).not.toMatch(/[–—]/);
  });

  it('indexes every page by its path', () => {
    for (const page of AGENT_PAGES) {
      expect(AGENT_PAGE_BY_PATH[page.path]).toBe(page);
    }
  });

  it('lists only real pages in the sitemap', () => {
    for (const path of indexablePaths()) {
      expect(AGENT_PAGE_BY_PATH[path]).toBeDefined();
    }
    expect(indexablePaths()).toContain('/');
  });
});

describe('markdownPath', () => {
  it('gives the home page a name rather than a bare extension', () => {
    expect(markdownPath('/')).toBe('/index.md');
  });

  it('appends the extension to an ordinary path', () => {
    expect(markdownPath('/pricing')).toBe('/pricing.md');
  });

  it('does not produce a double slash from a trailing one', () => {
    expect(markdownPath('/pricing/')).toBe('/pricing.md');
  });

  it('reaches every page, with no two pages colliding on one address', () => {
    const addresses = AGENT_PAGES.map((p) => markdownPath(p.path));
    expect(new Set(addresses).size).toBe(addresses.length);
    for (const page of AGENT_PAGES) {
      expect(AGENT_PAGE_BY_MARKDOWN_PATH[markdownPath(page.path)]).toBe(page);
    }
  });
});

describe('llms.txt', () => {
  const body = llmsTxt(BASE);

  it('opens with an H1 and a blockquote summary, per llmstxt.org', () => {
    const lines = body.split('\n');
    expect(lines[0].startsWith('# ')).toBe(true);
    expect(body).toMatch(/\n> /);
  });

  it('names every page, with an absolute URL', () => {
    for (const page of AGENT_PAGES) {
      expect(body).toContain(`${BASE}${page.path}`);
    }
  });

  it('names the markdown address of every page, so nothing depends on negotiation', () => {
    for (const page of AGENT_PAGES) {
      expect(body).toContain(`${BASE}${markdownPath(page.path)}`);
    }
  });

  it('tolerates a base URL with a trailing slash without doubling it', () => {
    expect(llmsTxt(`${BASE}/`)).not.toContain(`${BASE}//`);
  });

  it('sends a reader to the accuracy policy before they quote a score', () => {
    expect(body).toContain(`${BASE}/accuracy`);
  });

  it('says the tokenised reports are deliberately not listed', () => {
    expect(body).toContain('/r/');
  });
});
