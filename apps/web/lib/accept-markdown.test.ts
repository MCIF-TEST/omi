import { describe, it, expect } from 'vitest';

import { MARKDOWN_TYPE, VARY, prefersMarkdown } from './accept-markdown';

/**
 * The whole risk in this module is the direction of the mistake.
 *
 * Serving HTML to an agent that asked for markdown costs that agent one wasted parse. Serving
 * markdown to a browser downloads a text file instead of the site, for every human visitor, and it
 * is a one-character mistake away at all times because browsers put `*\/*` in every Accept header
 * they send.
 */

const BROWSER = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8';

describe('prefersMarkdown', () => {
  it('serves HTML to a browser', () => {
    expect(prefersMarkdown(BROWSER)).toBe(false);
  });

  it('does not read a wildcard as a request for markdown', () => {
    expect(prefersMarkdown('*/*')).toBe(false);
    expect(prefersMarkdown('text/*')).toBe(false);
  });

  it('serves markdown when it is asked for outright', () => {
    expect(prefersMarkdown('text/markdown')).toBe(true);
    expect(prefersMarkdown('text/x-markdown')).toBe(true);
  });

  it('serves markdown when it outranks HTML on q-value', () => {
    expect(prefersMarkdown('text/markdown,text/html;q=0.5')).toBe(true);
    expect(prefersMarkdown('text/html;q=0.9,text/markdown;q=1.0')).toBe(true);
  });

  it('serves HTML on a tie, because a client that wants both is a browser', () => {
    expect(prefersMarkdown('text/markdown,text/html')).toBe(false);
    expect(prefersMarkdown('text/markdown;q=0.8,text/html;q=0.8')).toBe(false);
  });

  it('serves HTML when HTML outranks markdown', () => {
    expect(prefersMarkdown('text/html,text/markdown;q=0.1')).toBe(false);
  });

  it('is not fooled by a wildcard sitting beside markdown at a lower quality', () => {
    expect(prefersMarkdown('text/markdown;q=0.9,*/*;q=0.8')).toBe(true);
  });

  it('treats an absent or empty header as a browser', () => {
    expect(prefersMarkdown(null)).toBe(false);
    expect(prefersMarkdown('')).toBe(false);
  });

  it('ignores case and whitespace, which real clients vary on', () => {
    expect(prefersMarkdown(' TEXT/MARKDOWN ')).toBe(true);
  });

  it('survives a malformed q-value rather than throwing', () => {
    expect(() => prefersMarkdown('text/markdown;q=banana')).not.toThrow();
    expect(prefersMarkdown('text/markdown;q=banana')).toBe(true);
  });
});

describe('the negotiated response contract', () => {
  it('names Accept in Vary, which is the whole point of the header', () => {
    expect(VARY).toContain('Accept');
    // Accept-Encoding too: dropping it would tell a cache that a gzip and an identity response are
    // interchangeable.
    expect(VARY).toContain('Accept-Encoding');
  });

  it('declares a charset, so an agent does not have to guess at the encoding', () => {
    expect(MARKDOWN_TYPE).toBe('text/markdown; charset=utf-8');
  });
});
