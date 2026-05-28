import Link from 'next/link';
import { ArrowLeft, User } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';

export default function AuthorNotFound() {
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
          <User size={10} />
          Author not tracked
        </CardLabel>
        <CardTitle>No comments by this author yet</CardTitle>
        <p className="text-sm text-fg-dim max-w-md mb-4">
          This author has never appeared in a scanned thread. Their footprint
          will populate the moment one of their comments shows up in any future
          content scan.
        </p>
        <Link
          href="/content"
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
        >
          <ArrowLeft size={11} />
          Back to content
        </Link>
      </Card>
    </div>
  );
}
