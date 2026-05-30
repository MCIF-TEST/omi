import { PageHeaderSkeleton, StatRowSkeleton, CardGridSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading channel" className="space-y-6">
      <PageHeaderSkeleton />
      <StatRowSkeleton />
      <CardGridSkeleton count={4} cols="lg:grid-cols-2" />
    </div>
  );
}
