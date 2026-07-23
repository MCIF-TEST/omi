'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Search, Loader2, X } from 'lucide-react';
import { listFeedback, type FeedbackEntry } from '@/lib/api';

const CATEGORY_TONE: Record<string, string> = {
  bug: 'text-danger border-danger/40',
  idea: 'text-accent-text border-accent/40',
  praise: 'text-tier-low border-tier-low/40',
  general: 'text-fg-mute border-border-2',
  other: 'text-fg-mute border-border-2',
};

export function FeedbackQueue() {
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<FeedbackEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const debounce = useRef<ReturnType<typeof setTimeout>>();

  const load = useCallback(async (query: string) => {
    setLoading(true);
    try {
      const res = await listFeedback({ q: query || undefined, limit: 200 });
      setRows(res.feedback);
      setTotal(res.total);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(''); }, [load]);

  // Debounced search as you type.
  useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { void load(q.trim()); }, 250);
    return () => clearTimeout(debounce.current);
  }, [q, load]);

  const fmt = useMemo(
    () => (iso: string) => {
      try { return new Date(iso).toLocaleString(); } catch { return iso; }
    },
    [],
  );

  return (
    <div className="space-y-4">
      <div className="relative max-w-md">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search message or email…"
          className="h-10 w-full pl-10 pr-9 text-sm rounded-lg bg-bg-inset border border-border-2 text-fg
                     placeholder:text-fg-faint focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline"
        />
        {q && (
          <button onClick={() => setQ('')} aria-label="Clear" className="absolute right-2.5 top-1/2 -translate-y-1/2 text-fg-mute hover:text-fg p-1">
            <X size={14} />
          </button>
        )}
      </div>

      <p className="font-mono text-2xs tracking-wider text-fg-faint">
        {loading ? <span className="inline-flex items-center gap-1.5"><Loader2 size={12} className="animate-spin" /> Loading…</span>
          : `${total} ${total === 1 ? 'entry' : 'entries'}${q ? ' matching' : ''}`}
      </p>

      {!loading && rows.length === 0 ? (
        <div className="rounded-xl border border-border-1 bg-bg-elev p-8 text-center text-sm text-fg-mute">
          No feedback {q ? 'matches your search' : 'yet'}.
        </div>
      ) : (
        <ul className="space-y-2.5">
          {rows.map((f) => (
            <li key={f.id} className="rounded-xl border border-border-1 bg-bg-elev p-4">
              <div className="flex items-center gap-2 flex-wrap mb-2">
                <span className={`font-mono text-[0.6rem] tracking-wider uppercase border rounded px-1.5 py-0.5 ${CATEGORY_TONE[f.category] ?? CATEGORY_TONE.other}`}>
                  {f.category}
                </span>
                <span className="font-mono text-xs text-fg-mute truncate">{f.email ?? 'anonymous'}</span>
                {f.page && <span className="font-mono text-[0.65rem] text-fg-faint truncate">· {f.page}</span>}
                <span className="font-mono text-[0.65rem] text-fg-faint ml-auto">{fmt(f.created_at)}</span>
              </div>
              <p className="text-sm text-fg-dim leading-relaxed whitespace-pre-wrap break-words">{f.message}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
