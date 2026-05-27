import Link from 'next/link';
import { ArrowLeft, Telescope } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';

export default function NarrativeNotFound() {
  return (
    <div className="space-y-4">
      <Link
        href="/narratives"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
      >
        <ArrowLeft size={11} />
        Narratives
      </Link>
      <Card>
        <CardLabel className="flex items-center gap-1.5">
          <Telescope size={10} />
          Narrative not found
        </CardLabel>
        <CardTitle>This cluster no longer exists</CardTitle>
        <p className="text-sm text-fg-dim max-w-md mb-4">
          Narrative clusters are rebuilt from scanned comments. This one may
          have been pruned, or the database was reset after a new deployment.
          Run a fresh scan to regenerate the narrative store.
        </p>
        <Link
          href="/narratives"
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
        >
          <ArrowLeft size={11} />
          Back to narratives
        </Link>
      </Card>
    </div>
  );
}
