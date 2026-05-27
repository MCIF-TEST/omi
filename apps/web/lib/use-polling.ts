'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Generic polling hook. Calls ``fetcher`` immediately and again every
 * ``intervalMs``. Stops polling while the tab is hidden to save quota.
 * Manual ``refresh()`` returned for explicit re-fetch.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): { data: T | null; error: Error | null; loading: boolean; refresh: () => Promise<void> } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const v = await fetcherRef.current();
      if (mounted.current) {
        setData(v);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e : new Error(String(e)));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    refresh();
    let id: ReturnType<typeof setInterval> | null = null;
    const start = () => {
      if (id != null) return;
      id = setInterval(() => { refresh(); }, intervalMs);
    };
    const stop = () => {
      if (id != null) { clearInterval(id); id = null; }
    };
    const visibility = () => {
      if (document.visibilityState === 'visible') {
        start();
        refresh();
      } else {
        stop();
      }
    };
    start();
    document.addEventListener('visibilitychange', visibility);
    return () => {
      mounted.current = false;
      stop();
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [intervalMs, refresh]);

  return { data, error, loading, refresh };
}
