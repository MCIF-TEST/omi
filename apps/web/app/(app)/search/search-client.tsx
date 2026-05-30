'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Search, ArrowRight, Clock, Users } from 'lucide-react';
import { TierBadge } from '@/components/shared/tier-badge';
import { ProbabilityBar } from '@/components/shared/probability-bar';
import { apiClient, type AccountSearchResponse, type AccountSearchResult } from '@/lib/api';
import { timeAgo } from '@/lib/format';

export function SearchClient({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<AccountSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setSearched(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient<AccountSearchResponse>(
        `/v1/accounts/search?q=${encodeURIComponent(q.trim())}&limit=30`
      );
      setResults(res.results);
      setSearched(true);
    } catch (e: any) {
      setError(e.message || 'Search failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialQuery.length >= 2) {
      runSearch(initialQuery);
    }
  }, [initialQuery, runSearch]);

  const handleChange = (v: string) => {
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const params = new URLSearchParams();
      if (v.trim()) params.set('q', v.trim());
      router.replace(`/search${params.size ? '?' + params.toString() : ''}`, { scroll: false });
      runSearch(v);
    }, 350);
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Intelligence database
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight mb-4">Account search</h1>

        {/* Search input */}
        <div className="relative">
          <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-fg-mute pointer-events-none" />
          <input
            type="text"
            value={query}
            onChange={(e) => handleChange(e.target.value)}
            placeholder="Search by handle, display name, or channel ID…"
            className="w-full pl-11 pr-4 py-3 bg-bg-elev border border-border-2 rounded-md text-fg placeholder:text-fg-faint focus:outline-none focus:border-accent text-sm"
            autoFocus
          />
          {loading && (
            <span className="absolute right-4 top-1/2 -translate-y-1/2 font-mono text-2xs text-fg-mute animate-pulse">
              searching…
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-fg-mute">
          Searches every account scanned on this platform. No credit cost.
        </p>
      </header>

      {error && (
        <p className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-sm px-4 py-3">
          {error}
        </p>
      )}

      {searched && results.length === 0 && !loading && (
        <div className="text-center py-12">
          <Users size={32} className="mx-auto text-fg-faint mb-3" />
          <p className="text-fg-dim text-sm">No accounts found for <strong className="text-fg">&quot;{query}&quot;</strong>.</p>
          <p className="text-xs text-fg-mute mt-1">Try a partial handle or YouTube channel ID (UC…).</p>
        </div>
      )}

      {results.length > 0 && (
        <div>
          <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-3">
            {results.length} result{results.length === 1 ? '' : 's'}
          </p>
          <ul className="space-y-2">
            {results.map((account) => (
              <AccountRow key={account.external_id} account={account} />
            ))}
          </ul>
        </div>
      )}

      {!searched && !loading && query.length < 2 && (
        <div className="text-center py-16">
          <Search size={40} className="mx-auto text-fg-faint mb-4" />
          <p className="text-fg-dim text-sm">
            Search by handle (e.g. <code className="text-accent">@username</code>), display name,
            or paste a YouTube channel ID.
          </p>
          <p className="text-xs text-fg-mute mt-2">
            Every commenter and channel you&apos;ve scanned is searchable here.
          </p>
        </div>
      )}
    </div>
  );
}

function AccountRow({ account }: { account: AccountSearchResult }) {
  const prob = account.overall_probability ?? 0;
  return (
    <li>
      <Link
        href={`/accounts/${encodeURIComponent(account.external_id)}?platform=${account.platform}`}
        className="flex items-center gap-4 p-4 bg-bg-elev border border-border-1 rounded-md hover:border-border-hot hover:bg-bg-elev-2/50 transition-colors group"
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3 mb-1 flex-wrap">
            <span className="font-semibold text-fg truncate">{account.handle}</span>
            {account.display_name && account.display_name !== account.handle && (
              <span className="text-sm text-fg-dim truncate">{account.display_name}</span>
            )}
            {account.tier && <TierBadge tier={account.tier} size="sm" />}
          </div>
          <div className="flex items-center gap-4 text-xs text-fg-mute font-mono tracking-wider flex-wrap">
            <span className="text-fg-faint truncate max-w-[200px]">{account.external_id}</span>
            {account.follower_count != null && (
              <span><Users size={10} className="inline mr-1" />{account.follower_count.toLocaleString()}</span>
            )}
            {account.last_scanned_at && (
              <span><Clock size={10} className="inline mr-1" />scanned {timeAgo(account.last_scanned_at)}</span>
            )}
          </div>
          {account.overall_probability != null && (
            <div className="mt-2 flex items-center gap-3">
              <ProbabilityBar value={prob} tier={account.tier ?? 'low'} showLabel={false} className="flex-1 h-1" />
              <span className="font-mono text-2xs text-fg-dim shrink-0">
                {Math.round(prob * 100)}% inauthentic
              </span>
            </div>
          )}
        </div>
        <ArrowRight size={14} className="text-fg-mute shrink-0 group-hover:text-fg transition-colors" />
      </Link>
    </li>
  );
}
