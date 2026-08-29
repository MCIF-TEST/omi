import { ClaimHandoff } from './claim-handoff';

export const metadata = { title: 'Setting up' };
export const dynamic = 'force-dynamic';

/**
 * The landing point after a funnel sign-up.
 *
 * A visitor read someone's public report, signed up from it, and arrives here. This page claims that
 * report into their archive and forwards them to the compile step for the same post, so the very
 * next thing they see is the comment section they came to check rather than an empty dashboard.
 *
 * Nothing renders for long: it is a handoff, not a destination.
 */
export default function WelcomePage({
  searchParams,
}: {
  searchParams: { claim?: string };
}) {
  const claim = typeof searchParams.claim === 'string' ? searchParams.claim : '';
  return <ClaimHandoff tokenFromUrl={claim} />;
}
