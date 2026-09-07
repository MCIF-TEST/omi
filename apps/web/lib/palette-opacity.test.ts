import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * An opacity modifier on a palette token generates NOTHING in this stylesheet.
 *
 * `bg-accent/10`, `border-accent/40`, `bg-tier-elevated/5` and every shape like them are absent
 * from the built CSS. The element renders with no ground and no border, and typecheck, lint and
 * every unit test stay green, because nothing in the toolchain knows the class was supposed to
 * exist. This repo has already shipped that once: the first render of the evidence grid was
 * entirely hollow for exactly this reason.
 *
 * MEASURED, NOT ASSUMED. Against the built stylesheet at the time of writing:
 *
 *     bg-accent/10            0 occurrences
 *     border-accent/40        0
 *     bg-tier-elevated/5      0
 *     bg-bg-elev-2            1
 *     border-accent           1
 *     text-accent             1
 *
 * so the fix is a real token plus a hairline, which is the instrument grammar the design language
 * already asks for: colour carried by a 1px rule rather than by a tinted fill.
 *
 * WHY THIS GUARD IS SCOPED RATHER THAN REPO-WIDE. About 200 of these already exist across
 * `apps/web`, including the filter chips in this very queue. Fixing them is a palette change that
 * would restyle every page, and CLAUDE.md records it as the owner's call, deliberately unfixed. A
 * repo-wide assertion would therefore fail on day one and be deleted by the next person. This one
 * covers the files added with the coordination redesign, so the rule is "do not add more" rather
 * than an unactionable "fix all of it".
 */

const GUARDED = [
  'components/shared/coordination-nav.tsx',
  'components/shared/stage-rail.tsx',
  'app/(app)/netdetect/run-panel.tsx',
];

/** `bg-`, `border-` or `text-` on a palette token with an opacity modifier. */
const DEAD = /\b(?:bg|border|text|ring|fill|stroke)-(?:accent|tier-[a-z]+|violet|bg-elev\d?|border-\d)[a-z0-9-]*\/\d+/g;

/** Comment lines, where these strings appear on purpose to explain the rule. */
function stripComments(source: string): string {
  return source
    .split('\n')
    .filter((line) => {
      const t = line.trim();
      return !t.startsWith('//') && !t.startsWith('*') && !t.startsWith('/*');
    })
    .join('\n');
}

describe('palette tokens with an opacity modifier', () => {
  for (const file of GUARDED) {
    it(`${file} uses none, because they render as nothing`, () => {
      const source = readFileSync(join(process.cwd(), file), 'utf8');
      const found = stripComments(source).match(DEAD) ?? [];
      expect(
        found,
        `${file} uses ${found.join(', ')}, which generate no CSS. Use a real token: a hairline in ` +
          'the semantic colour (border-tier-elevated) over bg-bg-elev-2, rather than a tinted fill.',
      ).toEqual([]);
    });
  }

  it('the pattern actually matches the shapes it is meant to catch', () => {
    // A guard nobody has seen fire is a guard nobody knows works, and a regex that matched nothing
    // would pass every file above forever.
    const sample = "className={cn('border-accent/40 bg-tier-elevated/5 text-tier-high/80')}";
    expect(sample.match(DEAD)).toEqual([
      'border-accent/40',
      'bg-tier-elevated/5',
      'text-tier-high/80',
    ]);
  });

  it('does not fire on the tokens that do generate CSS', () => {
    const good = "className='border-accent bg-bg-elev-2 text-accent border-border-1 bg-tier-low'";
    expect(good.match(DEAD)).toBeNull();
  });

  it('does not fire on ordinary fractions that are not palette classes', () => {
    // `w-1/2` and friends are real Tailwind and must not be swept up.
    expect("className='w-1/2 h-1/3 basis-2/3'".match(DEAD)).toBeNull();
  });
});
