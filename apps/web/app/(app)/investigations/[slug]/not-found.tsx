import Link from 'next/link';
import { ArrowLeft, FileSearch } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';

export default function InvestigationNotFound() {
  return (
    <div className="space-y-4">
      <Link
        href="/investigations"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
      >
        <ArrowLeft size={11} />
        Investigations
      </Link>
      <Card>
        <CardLabel className="flex items-center gap-1.5">
          <FileSearch size={10} />
          Investigation not found
        </CardLabel>
        <CardTitle>This investigation doesn&apos;t exist</CardTitle>
        <p className="text-sm text-fg-dim max-w-md mb-4">
          The link may be wrong, the investigation may have been removed, or it
          belongs to a different account. Saved investigations live under your
          own workspace.
        </p>
        <Link
          href="/investigations"
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
        >
          <ArrowLeft size={11} />
          Back to investigations
        </Link>
      </Card>
    </div>
  );
}
