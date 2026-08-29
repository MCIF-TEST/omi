import { CommenterSelect } from './commenter-select';

export const metadata = { title: 'Investigate' };

export default function InvestigatePage({
  searchParams,
}: {
  // `claimed` is the slug of a report just claimed from a shared link (see /welcome). Its presence is
  // what tells this page the visitor arrived through the funnel rather than starting from scratch, so
  // it can say where the report went and what their free credit is for.
  searchParams: { url?: string; claimed?: string };
}) {
  return (
    <CommenterSelect
      initialUrl={searchParams.url || ''}
      claimedSlug={searchParams.claimed || ''}
    />
  );
}
