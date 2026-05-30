import { PageHeaderSkeleton, DetailSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading author" className="space-y-6">
      <PageHeaderSkeleton />
      <DetailSkeleton />
    </div>
  );
}
