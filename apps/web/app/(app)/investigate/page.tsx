import { Workspace } from './workspace';

export const metadata = { title: 'Investigate — OMISPHERE' };

export default function InvestigatePage({
  searchParams,
}: {
  searchParams: { url?: string };
}) {
  return <Workspace initialUrl={searchParams.url || ''} />;
}
