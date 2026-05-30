import { PageHeaderSkeleton, StatRowSkeleton, ListSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading content" className="space-y-6">
      <PageHeaderSkeleton />
      <StatRowSkeleton />
      <ListSkeleton rows={6} />
    </div>
  );
}
