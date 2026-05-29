'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { apiClient, type OmiScore } from '@/lib/api';
import { ThreatBreakdown } from './threat-breakdown';

/**
 * Lazily fetches the OmiScore intelligence verdict for a single account and
 * renders the threat breakdown. Used in the commenter detail panel — the
 * account is already persisted by the scan, so this is a cheap read.
 *
 * Silently renders nothing if the account has no OmiScore yet (404) so it
 * never disrupts the detail layout.
 */
export function CommenterThreatPanel({
  platform,
  externalId,
}: {
  platform: string;
  externalId: string;
}) {
  const [score, setScore] = useState<OmiScore | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'empty'>('loading');

  useEffect(() => {
    let cancelled = false;
    setState('loading');
    setScore(null);
    apiClient<OmiScore>(`/v1/intelligence/account/${platform}/${encodeURIComponent(externalId)}`)
      .then((s) => {
        if (cancelled) return;
        setScore(s);
        setState('ready');
      })
      .catch(() => {
        if (cancelled) return;
        // 404 (no scan history) or any error — hide the section silently
        // so it never disrupts the detail layout.
        setState('empty');
      });
    return () => { cancelled = true; };
  }, [platform, externalId]);

  if (state === 'empty') return null;

  return (
    <section>
      <div className="flex items-center gap-1.5 font-mono text-2xs tracking-[0.18em] text-accent uppercase mb-3">
        OmiScore intelligence
      </div>
      {state === 'loading' ? (
        <div className="flex items-center gap-2 py-6 justify-center text-fg-mute font-mono text-2xs tracking-wider uppercase">
          <Loader2 size={13} className="animate-spin" />
          Composing verdict…
        </div>
      ) : (
        score && <ThreatBreakdown score={score} />
      )}
    </section>
  );
}
