import { Skeleton } from '@/components/ui/skeleton';
import { PageHeaderSkeleton, CardGridSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading dashboard" className="space-y-8">
      <PageHeaderSkeleton />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-md border border-border-1 bg-bg-elev p-4 space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-7 w-16" />
          </div>
        ))}
      </div>
      <CardGridSkeleton count={3} cols="sm:grid-cols-2 lg:grid-cols-3" />
    </div>
  );
}
