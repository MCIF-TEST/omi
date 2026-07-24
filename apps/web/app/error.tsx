'use client';

// Route-segment error boundary. Without this, ANY error thrown while rendering a page shows Next's
// bare "Application error / Digest: …" screen. This catches it and offers a real recovery path, so a
// transient failure (a slow API, a token hiccup) never strands the user on a dead page.
import { useEffect } from 'react';
import Link from 'next/link';
import { RotateCw } from 'lucide-react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the digest in the browser console so a report can be tied to the server log line.
    console.error('omisphere route error', error.digest, error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div className="max-w-md w-full text-center space-y-5">
        <h1 className="display text-2xl font-semibold tracking-tight text-fg">Something went wrong</h1>
        <p className="text-sm text-fg-mute">
          This page hit an unexpected error. It&apos;s usually temporary — try again, or head back and
          reopen it.
        </p>
        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="inline-flex items-center gap-2 btn-lamp font-semibold px-5 py-2.5 rounded-lg text-sm"
          >
            <RotateCw size={14} />
            Try again
          </button>
          <Link
            href="/investigate"
            className="font-mono text-2xs tracking-wider uppercase text-fg-mute hover:text-fg-dim transition-colors"
          >
            Back to app
          </Link>
        </div>
        {error.digest && (
          <p className="font-mono text-2xs text-fg-faint">Reference: {error.digest}</p>
        )}
      </div>
    </div>
  );
}
