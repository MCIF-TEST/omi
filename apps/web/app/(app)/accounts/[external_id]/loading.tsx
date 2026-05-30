import { DetailSkeleton } from '@/components/shared/loading-skeletons';

export default function Loading() {
  return (
    <div role="status" aria-label="Loading account">
      <DetailSkeleton />
    </div>
  );
}
