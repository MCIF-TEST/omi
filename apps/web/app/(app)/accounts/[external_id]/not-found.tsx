import Link from 'next/link';
import { ArrowLeft, UserX } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';

export default function AccountNotFound() {
  return (
    <div className="space-y-4">
      <Link
        href="/content"
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider text-fg-dim hover:text-fg uppercase transition-colors"
      >
        <ArrowLeft size={11} />
        Content
      </Link>
      <Card>
        <CardLabel className="flex items-center gap-1.5">
          <UserX size={10} />
          Account not found
        </CardLabel>
        <CardTitle>No scan history for this account</CardTitle>
        <p className="text-sm text-fg-dim max-w-md mb-4">
          This account hasn&apos;t been scanned yet, or the identifier is
          invalid. Account profiles are built from scans — run one to populate
          this page, or check that the channel ID is correct.
        </p>
        <Link
          href="/investigate"
          className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors"
        >
          <ArrowLeft size={11} />
          Start a scan
        </Link>
      </Card>
    </div>
  );
}
