import { PageHeaderSkeleton, CardGridSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading narratives" className="space-y-6">
      <PageHeaderSkeleton />
      <CardGridSkeleton count={6} cols="lg:grid-cols-2" />
    </div>
  );
}
