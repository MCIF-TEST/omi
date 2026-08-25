import { getCurrentUser } from '@/lib/auth';
import { BulkClient } from './bulk-client';
import { ConsoleHeader, SECTION_INDEX } from '@/components/shared/console-header';

export const metadata = { title: 'Bulk scan' };

export default async function BulkPage() {
  const user = await getCurrentUser();
  return (
    <div className="space-y-6">
      <ConsoleHeader
        index={SECTION_INDEX['/bulk']}
        eyebrow="Intelligence · Workflow"
        title="Bulk scan"
        lede={<>Paste up to 20 YouTube video or channel URLs. OMISPHERE scans them sequentially in the background. Come back when it&apos;s done. Each URL costs 1 credit; failed scans are refunded automatically.</>}
      />
      <BulkClient credits={user?.credits_remaining ?? 0} />
    </div>
  );
}
