import Link from 'next/link';
import { ArrowLeft, Database } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';

export default function ContentNotFound() {
  return (
    <div className="space-y-4">
      <Link
        href="/content"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
      >
        <ArrowLeft size={11} />
        Content database
      </Link>
      <Card>
        <CardLabel className="flex items-center gap-1.5">
          <Database size={10} />
          Content not in database
        </CardLabel>
        <CardTitle>This content has never been scanned</CardTitle>
        <p className="text-sm text-fg-dim max-w-md mb-4">
          OMISPHERE only tracks content that someone has actively scanned. Run
          a scan from the Investigate page and this entity will appear here —
          along with every batch, comment, and coordination signal collected
          from it across all users.
        </p>
        <div className="flex flex-wrap gap-2">
          <Link
            href="/investigate"
            className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
          >
            Run a scan
          </Link>
          <Link
            href="/content"
            className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
          >
            <ArrowLeft size={11} />
            Browse database
          </Link>
        </div>
      </Card>
    </div>
  );
}
