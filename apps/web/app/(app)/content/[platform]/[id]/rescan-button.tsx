'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2, Plus, AlertCircle } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';

export function RescanButton({
  platform,
  contentId,
  hasContinuation,
}: {
  platform: string;
  contentId: string;
  hasContinuation: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setErr(null);
    setInfo(null);
    try {
      const result = await apiClient<{
        commenter_count: number;
        coordination_score: number;
        next_page_token: string | null;
      }>(`/v1/content/${platform}/${contentId}/rescan`, { method: 'POST' });
      setInfo(
        `+${result.commenter_count} commenters · coord ${Math.round(result.coordination_score * 100)}%`,
      );
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.status === 402) setErr('Out of credits.');
        else if (e.status === 501) setErr('Not yet supported on this platform.');
        else setErr(e.message);
      } else {
        setErr('Scan failed. Try again.');
      }
    } finally {
      setBusy(false);
    }
  }

  const label = hasContinuation ? '+ New batch' : 'Rescan from start';
  const subtitle = hasContinuation
    ? 'Resumes from cursor — fetches only new comments'
    : 'Re-reads from page 1 (dedupes existing)';

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={run}
        disabled={busy}
        className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        title={subtitle}
      >
        {busy ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
        {busy ? 'Scanning…' : label}
      </button>
      <span className="font-mono text-2xs text-fg-faint">{subtitle}</span>
      {info && <span className="font-mono text-2xs text-tier-low">{info}</span>}
      {err && (
        <span className="inline-flex items-center gap-1 font-mono text-2xs text-tier-high">
          <AlertCircle size={10} /> {err}
        </span>
      )}
    </div>
  );
}
