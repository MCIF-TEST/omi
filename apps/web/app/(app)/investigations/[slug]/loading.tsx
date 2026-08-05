import { PageHeaderSkeleton } from '@/components/shared/loading-skeletons';
import { AnalysisProgress } from '@/components/shared/analysis-progress';

/**
 * The route skeleton, shown while the investigation page's data loads.
 *
 * The body deliberately renders the SAME progress card the page itself shows a moment later,
 * rather than grey block skeletons. Coming from the scan step, a user used to watch the violet
 * progress card become grey rectangles and then become a violet progress card again, which reads
 * as the job restarting rather than a route transition. The page header keeps a skeleton because
 * its content (the post title and URL) genuinely is not known yet.
 *
 * No batch count is passed: this render knows nothing about the investigation, and inventing a
 * denominator here is exactly the thing `analysis-progress.tsx` is careful not to do.
 */
export default function Loading() {
  return (
    <div role="status" aria-label="Loading investigation" className="space-y-6">
      <PageHeaderSkeleton />
      <AnalysisProgress elapsedSec={0} />
    </div>
  );
}
