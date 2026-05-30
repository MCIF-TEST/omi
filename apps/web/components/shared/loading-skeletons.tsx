import { Skeleton } from '@/components/ui/skeleton';

/**
 * Reusable loading scaffolds for route-level loading.tsx files. Each mirrors
 * the *shape* of the page it stands in for — a header, then content — so the
 * transition into real data is calm rather than a jarring pop-in.
 *
 * All pieces are aria-hidden via Skeleton; the wrappers add role="status"
 * so assistive tech announces "loading" once, not a wall of empty boxes.
 */

export function PageHeaderSkeleton() {
  return (
    <div className="space-y-2.5">
      <Skeleton className="h-3 w-32" />
      <Skeleton className="h-8 w-64 max-w-[70%]" />
      <Skeleton className="h-4 w-80 max-w-[85%]" />
    </div>
  );
}

export function CardGridSkeleton({ count = 6, cols = 'md:grid-cols-2' }: { count?: number; cols?: string }) {
  return (
    <div className={`grid grid-cols-1 ${cols} gap-3`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border-1 bg-bg-elev p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-2 w-full" />
          <div className="grid grid-cols-4 gap-2 pt-1">
            {Array.from({ length: 4 }).map((_, j) => (
              <Skeleton key={j} className="h-8" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function StatRowSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-md border border-border-1 bg-bg-elev p-3 space-y-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-6 w-16" />
        </div>
      ))}
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="rounded-2xl border border-border-1 bg-bg-elev p-5 flex items-start gap-5">
        <Skeleton className="h-[88px] w-[88px] rounded-full shrink-0" />
        <div className="flex-1 space-y-2.5 min-w-0">
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="h-7 w-1/2" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-full max-w-md" />
        </div>
      </div>
      {/* Sections */}
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-16 w-full rounded-xl" />
        </div>
      ))}
    </div>
  );
}

export function ListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border-1 bg-bg-elev p-4">
          <Skeleton className="h-9 w-9 rounded-lg shrink-0" />
          <div className="flex-1 space-y-1.5 min-w-0">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-5 w-12 rounded-full shrink-0" />
        </div>
      ))}
    </div>
  );
}
