import { CommenterSelect } from './commenter-select';

export const metadata = { title: 'Investigate. OMISPHERE' };

export default function InvestigatePage({
  searchParams,
}: {
  searchParams: { url?: string };
}) {
  return <CommenterSelect initialUrl={searchParams.url || ''} />;
}
