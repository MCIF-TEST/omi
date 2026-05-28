import Link from 'next/link';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export default function ChannelNotFound() {
  return (
    <Card>
      <CardLabel>Not found</CardLabel>
      <CardTitle>Channel not in database</CardTitle>
      <p className="text-sm text-fg-dim mb-5">
        This channel has not been scanned yet. Scan one of their videos first — the
        channel intelligence view is built automatically from video scan data.
      </p>
      <Link href="/content">
        <Button variant="secondary">Browse content database</Button>
      </Link>
    </Card>
  );
}
