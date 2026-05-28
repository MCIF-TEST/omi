import { Suspense } from 'react';
import { SearchClient } from './search-client';

export const metadata = { title: 'Account Search — OMISPHERE' };

export default function SearchPage({
  searchParams,
}: {
  searchParams: { q?: string };
}) {
  return (
    <Suspense fallback={<div className="p-8 text-fg-mute text-sm">Loading…</div>}>
      <SearchClient initialQuery={searchParams.q ?? ''} />
    </Suspense>
  );
}
