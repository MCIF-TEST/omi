import { getCurrentUser } from '@/lib/auth';
import { BulkClient } from './bulk-client';

export const metadata = { title: 'Bulk scan — OMISPHERE' };

export default async function BulkPage() {
  const user = await getCurrentUser();
  return (
    <div className="space-y-6">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Workflow
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">Bulk scan</h1>
        <p className="mt-1 text-sm text-fg-dim max-w-xl">
          Paste up to 20 YouTube video or channel URLs. OMISPHERE scans them
          sequentially in the background — come back when it&apos;s done.
          Each URL costs 1 credit; failed scans are refunded automatically.
        </p>
      </header>
      <BulkClient credits={user?.credits_remaining ?? 0} />
    </div>
  );
}
