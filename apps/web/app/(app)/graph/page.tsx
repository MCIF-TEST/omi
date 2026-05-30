import { GraphClient } from './graph-client';

export const metadata = { title: 'My Graphs — OMISPHERE' };
export const dynamic = 'force-dynamic';

export default function GraphPage() {
  return <GraphClient />;
}
