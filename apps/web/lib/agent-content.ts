/**
 * What an agent gets instead of the rendered page.
 *
 * ONE MODULE, because four surfaces have to agree and nothing at runtime reconciles them: the
 * sitemap, the markdown served by content negotiation, the llms.txt index, and the recovery links
 * on a 404. A page added to one and forgotten in the others is the failure mode this file exists to
 * remove, and it is invisible from the browser because every one of those surfaces is only ever
 * read by a machine.
 *
 * The markdown is written by hand rather than derived from the JSX, and that is a deliberate
 * trade. Scraping our own components would produce navigation chrome, button labels and
 * accessibility text that mean nothing out of context. An agent asking for markdown wants the
 * page's CLAIMS, not its furniture.
 *
 * Keep the prose here honest. It is the version of the site a machine quotes, so anything it
 * overstates is overstated in a context where nobody can see the surrounding page to correct it.
 */

export interface AgentPage {
  path: string;
  title: string;
  /** One line for llms.txt and for the 404 recovery list. */
  summary: string;
  /** The page as markdown, served under `Accept: text/markdown`. */
  markdown: string;
  /** Whether the sitemap should list it. Everything here is public; this marks the indexable ones. */
  indexable?: boolean;
}

const BRAND = 'OmiSphere';

export const AGENT_PAGES: AgentPage[] = [
  {
    path: '/',
    title: `${BRAND}: coordinated inauthentic behaviour detection`,
    summary: 'What OmiSphere does, how a scan works, and what the scores mean.',
    indexable: true,
    markdown: `# ${BRAND}

${BRAND} analyses the comment section of a social media post and reports which accounts show signs
of being bought, automated, or coordinated.

## How a scan works

1. Paste a link to an X post or a YouTube video.
2. ${BRAND} compiles the accounts that commented. This step is free.
3. You choose which of those accounts to analyse.
4. Each selected account is scored, and an AI analyst writes a per-account read explaining the score
   against evidence you can check.

## What a score is

Every analysed account gets an OMI score from 0 to 100 and a tier: low, moderate, elevated or high.
A score is a probabilistic reading of public behaviour. It is not a finding of fact, not an
allegation that anyone broke a law or a platform rule, and it carries no claim about who operates an
account, whether money changed hands, or anyone's intent.

Businesses, fan accounts, news aggregators, new users and people writing in a second language all
legitimately resemble some of the patterns being measured. A low score is not a certification
either.

## Evidence behind every score

Eight dimensions are assessed per account: temporal, semantic, ai_writing, profile, voice,
engagement, account_maturity and history_authenticity. A dimension with no collected evidence is
reported as null rather than as zero, because "we could not tell" is not the same claim as "this
looks like a real person".

Claims about what an account wrote carry a verbatim quote, and figures such as follower ratios and
account age are computed rather than estimated. Prose that fails an automated check against the
account's real metadata is withheld rather than published.

## Platforms

X and YouTube are live. Reddit is next.

## Links

- Pricing: /pricing
- What the scores mean and how to dispute one: /accuracy
- About: /about
- Privacy: /privacy
- Terms: /terms
- Developer resources: /developers
`,
  },
  {
    path: '/pricing',
    title: `Pricing. ${BRAND}`,
    summary: 'Three plans, what each includes, and how credits are charged.',
    indexable: true,
    markdown: `# Pricing. ${BRAND}

Compiling a comment section is free. Credits are spent only on the accounts you choose to scan.

One credit covers 20 accounts, on every platform.

## Plans

| Plan | Price | Credits | Accounts per month |
| --- | --- | --- | --- |
| Starter | $14.99/mo | 12 | 240 |
| Reporter | $79/mo | 75 | 1,500 |
| Research | $249/mo | 250 | 5,000 |

Reporter adds the eight-dimension breakdown behind every score, saved graphs, and monitoring.
Research adds coordination detection across your scans, evidence that accumulates between
investigations, and API access.

Running out does not end your month: credit packs are sold at $1 per credit.

Every plan includes a monthly lookup allowance far larger than its credits can spend. Loading a
comment section calls the platform, and those calls cost money whether or not you scan anyone, so
the allowance is what lets the plans be priced honestly.

## Links

- Full pricing page: /pricing
- What the scores mean: /accuracy
`,
  },
  {
    path: '/accuracy',
    title: `What the scores mean. ${BRAND}`,
    summary: 'The scope of a score, the shapes that resemble the patterns, and how to dispute a report.',
    indexable: true,
    markdown: `# What the scores mean. ${BRAND}

Read this before quoting a score.

## What a score is not

- Not a finding of fact. These are probabilistic readings of public behaviour.
- Not an allegation that anyone broke a law or a platform rule.
- No claim about who operates an account, whether money changed hands, or anyone's intent.

## Shapes that legitimately resemble the patterns

A business or brand account. A fan or hobby account. A news or aggregator feed. A real person who
is new to the platform. A dormant account that came back. A private person with a small footprint.
Someone writing in a second language or a non-Latin script. An account whose opinion is unpopular.

Digits at the end of a handle are appended automatically by platforms and are never a tell.

## A low score is not a certification

It means no mechanical tell was found in what was collected. A competent operation is not reliably
separable from a real person one account at a time.

## Disputing a report

Anyone named in a public ${BRAND} report can dispute it, without an account. Filing does not
automatically unpublish anything, because otherwise anyone could silence any report by claiming to
be named in it. Disputes are reviewed and a report can be withdrawn, which revokes the link
immediately including for copies already posted elsewhere.

## Links

- Dispute form: on any public report at /r/<token>
- Privacy: /privacy
`,
  },
  {
    path: '/about',
    title: `About. ${BRAND}`,
    summary: 'What OmiSphere is for and which platforms it covers.',
    indexable: true,
    markdown: `# About ${BRAND}

${BRAND} is an authenticity layer for social media comment sections. It scores individual accounts
for signs of automation, purchase and coordination, and explains each score against evidence a
reader can check.

X and YouTube are live. Reddit is next.

## Links

- What the scores mean: /accuracy
- Pricing: /pricing
- Developer resources: /developers
`,
  },
  {
    path: '/developers',
    title: `Developer resources. ${BRAND}`,
    summary: 'API base URL, OpenAPI specification, authentication, and machine-readable files.',
    indexable: true,
    markdown: `# Developer resources. ${BRAND}

${BRAND} exposes a JSON HTTP API. API access is included on the Research plan.

## Machine-readable files

- OpenAPI specification: /openapi.json
- Interactive API reference: /docs
- Agent index: /llms.txt
- Sitemap: /sitemap.xml
- Crawl rules: /robots.txt

## Content negotiation

Every public page is available as markdown. Send \`Accept: text/markdown\` and the response is
\`Content-Type: text/markdown\` with \`Vary: Accept\`.

## Errors

Errors are JSON. Every error body carries a stable machine-readable \`code\`, a human \`message\`, a
\`hint\` describing what to do about it, and a \`docs\` link. The legacy \`detail\` field is retained
so existing clients keep working.

\`\`\`json
{
  "error": {
    "code": "payment_required",
    "message": "Your plan does not include this feature.",
    "hint": "Upgrade the plan on the billing page, or buy a credit pack.",
    "docs": "https://omisphere.online/developers",
    "status": 402
  },
  "detail": "Your plan does not include this feature."
}
\`\`\`

## Authentication

Requests authenticate with a session cookie issued by the sign-in flow. Programmatic API keys are
not yet issued; contact us if you need one.

## Rate limits

Requests are limited per IP and per user. A refused request answers 429 with \`Retry-After\` and
\`X-RateLimit-*\` headers. A refusal never consumes credits.
`,
  },
  {
    path: '/privacy',
    title: `Privacy. ${BRAND}`,
    summary: 'What data is collected, which subprocessors are used, and how to object.',
    indexable: true,
    markdown: `# Privacy. ${BRAND}

${BRAND} analyses public social media content, including content authored by people who are not
${BRAND} users and did not agree to be analysed.

## Account data

Email address, authentication identifiers, credit balance and billing state, and the
investigations an account has run.

## Public social media data

Handles, display names, profile metadata, and public posts and comments retrieved from the
platform being scanned. This is collected indirectly, about people who are not our users.

## Subprocessors

Authentication, payments, hosting, and the model gateway the analyst runs on are provided by third
parties, alongside the platform APIs being scanned. The policy at /privacy names each one. No
third-party analytics are used.

## Coordination patterns across accounts

Evidence that two accounts behaved alike is retained across investigations, because one operation
seen by two customers is one operation. That record holds behaviour, not the identity of the
customer whose scan produced it.

## Your rights

Access, correction, deletion and objection. Anyone named in a public report can dispute it and
request its withdrawal, without holding an account. See /accuracy.

The full policy is at /privacy.
`,
  },
  {
    path: '/terms',
    title: `Terms. ${BRAND}`,
    summary: 'Subscription terms, what a score is and is not, and acceptable use.',
    indexable: true,
    markdown: `# Terms. ${BRAND}

## The service

${BRAND} scores public social media accounts for signs of automation, bought engagement and
coordination, and writes an explanation of each score.

## Credits and billing

Access is sold as a monthly subscription carrying credits. One credit covers 20 accounts.
Credits are consumed when a scan is run and are not refundable once the work has been performed.

## What the output is, and is not

A score is a probabilistic reading of public behaviour. It is not a finding of fact, not an
allegation that anyone broke a law or a platform rule, and it carries no claim about who operates
an account, whether money changed hands, or anyone's intent. Do not present a score as proof, and
read /accuracy before publishing one.

## Acceptable use

No harassment of the accounts analysed, no use of the output to target an individual, and no
scraping or resale of the service.

## Liability

The service is provided as is, without warranty. Liability is limited to the amount paid in the
preceding month.

The full terms of service are at /terms.
`,
  },
];

export const AGENT_PAGE_BY_PATH: Record<string, AgentPage> = Object.fromEntries(
  AGENT_PAGES.map((p) => [p.path, p]),
);

/**
 * The explicit markdown URL for a page, alongside the negotiated one.
 *
 * Negotiation alone is not enough, and the reason is a framework limitation this repo cannot fix
 * from inside itself: Next 14's app router calls `res.setHeader('vary', ...)` during render
 * (`base-server.js: setVaryHeader`), which OVERWRITES anything middleware set, so the HTML variant
 * of a negotiated URL ships `Vary: RSC, Next-Router-State-Tree, ...` and cannot be made to carry
 * `Accept`. The markdown variant is returned by middleware before that code ever runs, so it does
 * carry the correct `Vary`; the HTML half is the one a shared cache could still confuse.
 *
 * An addressable `.md` URL removes the dependency on negotiation entirely. It is one document at
 * one address, cacheable with no variants at all, and it is what `<link rel="alternate">`,
 * llms.txt and the 404 recovery list point at, so an agent never has to negotiate to get it.
 */
export function markdownPath(path: string): string {
  return path === '/' ? '/index.md' : `${path.replace(/\/+$/, '')}.md`;
}

export const AGENT_PAGE_BY_MARKDOWN_PATH: Record<string, AgentPage> = Object.fromEntries(
  AGENT_PAGES.map((p) => [markdownPath(p.path), p]),
);

/** Paths the sitemap should list. Derived, so a new page cannot be added and then forgotten. */
export function indexablePaths(): string[] {
  return AGENT_PAGES.filter((p) => p.indexable).map((p) => p.path);
}

/**
 * The llms.txt body.
 *
 * Follows the llmstxt.org shape: an H1 with the name, a blockquote summary, then link sections.
 * Deliberately terse. The point is to let an agent find the right page in one hop, not to be the
 * documentation.
 */
export function llmsTxt(base: string): string {
  const origin = base.replace(/\/$/, '');
  const link = (p: AgentPage) =>
    `- [${p.title}](${origin}${p.path}): ${p.summary} Markdown: ${origin}${markdownPath(p.path)}`;

  return `# ${BRAND}

> ${BRAND} analyses the comment section of a social media post and reports which accounts show signs
> of being bought, automated, or coordinated. Every score is explained against evidence a reader can
> check. X and YouTube are live; Reddit is next.

Scores are probabilistic readings of public behaviour, not findings of fact. Read
${origin}/accuracy before quoting one.

## Pages

${AGENT_PAGES.filter((p) => p.path !== '/developers').map(link).join('\n')}

## Developer

${[AGENT_PAGE_BY_PATH['/developers']].map(link).join('\n')}
- [OpenAPI specification](${origin}/openapi.json): Machine-readable description of the ${BRAND} HTTP API.
- [API reference](${origin}/docs): Interactive reference generated from the OpenAPI specification.

## Machine-readable

- [Sitemap](${origin}/sitemap.xml): Every indexable page.
- [Crawl rules](${origin}/robots.txt): What may be crawled.

## Notes

- Every page on this site is available as markdown, at its own \`.md\` address (listed
  above) and by sending \`Accept: text/markdown\` to the ordinary URL.
- API errors are JSON and carry a stable \`code\`, a \`message\`, a \`hint\` and a \`docs\` link.
- Report pages under /r/ are unlisted and reachable only by their token. They are deliberately
  excluded from the sitemap and disallowed in robots.txt.
`;
}
