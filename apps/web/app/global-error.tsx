'use client';

// Last-resort boundary for errors thrown in the ROOT layout itself (which app/error.tsx can't catch,
// because it lives inside that layout). Must render its own <html>/<body>. Kept dependency-free and
// self-contained so it can render even when almost everything else has failed.
import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('omisphere global error', error.digest, error);
  }, [error]);

  return (
    <html lang="en">
      <body
        style={{
          margin: 0,
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#010203',
          color: '#ffffff',
          fontFamily: 'Inter, system-ui, sans-serif',
          padding: '1.5rem',
        }}
      >
        <div style={{ maxWidth: '28rem', textAlign: 'center' }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.75rem' }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: '0.875rem', color: '#aab2bc', marginBottom: '1.25rem' }}>
            The app hit an unexpected error. Please try again.
          </p>
          <button
            onClick={reset}
            style={{
              background: '#3b82f6',
              color: '#fff',
              fontWeight: 600,
              border: 0,
              borderRadius: '0.625rem',
              padding: '0.625rem 1.25rem',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
          {error.digest && (
            <p style={{ fontFamily: 'monospace', fontSize: '0.7rem', color: '#7b8593', marginTop: '1rem' }}>
              Reference: {error.digest}
            </p>
          )}
        </div>
      </body>
    </html>
  );
}
