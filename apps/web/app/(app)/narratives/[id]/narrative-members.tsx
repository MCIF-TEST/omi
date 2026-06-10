'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { MessageSquare, Users, ChevronDown, X, Loader2, ExternalLink } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { apiClient } from '@/lib/api';
import { timeAgo } from '@/lib/format';

interface Member {
  account_external_id: string;
  handle: string | null;
  platform: string;
  comment_text: string;
  parent_id: string | null;
  observed_at: string;
  tier: string | null;
  score: number | null;
  scanned: boolean;
}

interface MembersResponse {
  narrative_id: number;
  label: string;
  total: number;
  distinct_authors: number;
  members: Member[];
}

const PAGE = 25;

const TIER_CLS: Record<string, string> = {
  high: 'text-tier-high border-tier-high/40 bg-tier-high/10',
  elevated: 'text-tier-elevated border-tier-elevated/40 bg-tier-elevated/10',
  moderate: 'text-tier-moderate border-tier-moderate/40 bg-tier-moderate/10',
  low: 'text-tier-low border-tier-low/40 bg-tier-low/10',
};

/**
 * Drill into a narrative's actual evidence: the comments and the commenters who
 * posted them — not just aggregate stats. Each commenter carries their OWN scan
 * verdict (tier/score) and links to their account page when scanned.
 */
export function NarrativeMembers({ narrativeId }: { narrativeId: number }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [total, setTotal] = useState(0);
  const [distinctAuthors, setDistinctAuthors] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<{ id: string; handle: string | null } | null>(null);

  const load = async (account: string | null, startOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ limit: String(PAGE), offset: String(startOffset) });
      if (account) qs.set('account_external_id', account);
      const res = await apiClient<MembersResponse>(
        `/v1/narratives/${narrativeId}/members?${qs.toString()}`,
      );
      setTotal(res.total);
      setDistinctAuthors(res.distinct_authors);
      setMembers((prev) => (startOffset === 0 ? res.members : [...prev, ...res.members]));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load comments.');
    } finally {
      setLoading(false);
    }
  };

  // Initial load (and re-load when the narrative changes).
  useEffect(() => {
    setMembers([]);
    setFilter(null);
    load(null, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [narrativeId]);

  const applyFilter = (m: Member | null) => {
    setMembers([]);
    setFilter(m ? { id: m.account_external_id, handle: m.handle } : null);
    load(m ? m.account_external_id : null, 0);
  };

  const accountHref = (m: Member) =>
    `/accounts/${encodeURIComponent(m.account_external_id)}?platform=${m.platform}` +
    (m.handle ? `&handle=${encodeURIComponent(m.handle)}` : '');

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 pt-5 pb-3 border-b border-border-1 flex items-center gap-2 flex-wrap">
        <CardLabel className="flex items-center gap-1.5 mb-0">
          <MessageSquare size={10} />
          Comments &amp; commenters in this narrative
        </CardLabel>
        <span className="font-mono text-2xs text-fg-faint inline-flex items-center gap-3 ml-auto">
          <span className="inline-flex items-center gap-1">
            <MessageSquare size={10} /> {total.toLocaleString()} comments
          </span>
          <span className="inline-flex items-center gap-1">
            <Users size={10} /> {distinctAuthors.toLocaleString()} commenters
          </span>
        </span>
      </div>

      {filter && (
        <div className="px-5 py-2 border-b border-border-1 bg-bg-elev/40 flex items-center gap-2">
          <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
            Filtered to
          </span>
          <span className="font-mono text-2xs text-fg">@{filter.handle ?? filter.id}</span>
          <button
            onClick={() => applyFilter(null)}
            className="ml-auto inline-flex items-center gap-1 font-mono text-2xs text-fg-dim hover:text-fg transition-colors"
          >
            <X size={11} /> clear
          </button>
        </div>
      )}

      {error && <p className="px-5 py-4 text-sm text-tier-elevated">{error}</p>}

      <ul className="divide-y divide-border-1">
        {members.map((m, i) => (
          <li key={`${m.account_external_id}:${m.observed_at}:${i}`} className="px-5 py-3">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              {m.scanned ? (
                <Link
                  href={accountHref(m)}
                  className="group inline-flex items-center gap-1 text-sm text-fg hover:text-accent font-medium transition-colors"
                >
                  @{m.handle ?? m.account_external_id}
                  <ExternalLink size={10} className="text-fg-faint group-hover:text-accent" />
                </Link>
              ) : (
                <span className="text-sm text-fg-dim font-medium">
                  @{m.handle ?? m.account_external_id}
                </span>
              )}

              {/* The commenter's OWN scan verdict, surfaced honestly. */}
              {m.tier ? (
                <span
                  className={`inline-flex items-center font-mono text-2xs tracking-wider uppercase px-1.5 py-0.5 rounded-sm border ${
                    TIER_CLS[m.tier] ?? 'text-fg-mute border-border-2'
                  }`}
                >
                  {m.tier}
                  {m.score != null && ` · ${Math.round(m.score * 100)}%`}
                </span>
              ) : (
                <span className="font-mono text-2xs text-fg-faint border border-border-2 rounded-sm px-1.5 py-0.5">
                  not scanned
                </span>
              )}

              <span className="font-mono text-2xs text-fg-mute uppercase">{m.platform}</span>
              <span className="font-mono text-2xs text-fg-faint ml-auto">
                {timeAgo(m.observed_at)}
              </span>
              {!filter && (
                <button
                  onClick={() => applyFilter(m)}
                  className="font-mono text-2xs text-fg-faint hover:text-accent transition-colors"
                  title="Show only this commenter's contributions to this narrative"
                >
                  filter
                </button>
              )}
            </div>
            <p className="text-sm text-fg leading-relaxed whitespace-pre-wrap break-words">
              {m.comment_text}
            </p>
          </li>
        ))}
      </ul>

      {members.length === 0 && !loading && !error && (
        <p className="px-5 py-6 text-sm text-fg-dim text-center">
          No member comments recorded for this narrative.
        </p>
      )}

      <div className="px-5 py-3 border-t border-border-1 flex items-center justify-between">
        <span className="font-mono text-2xs text-fg-faint">
          Showing {members.length.toLocaleString()} of {total.toLocaleString()}
        </span>
        {members.length < total && (
          <button
            onClick={() => load(filter ? filter.id : null, members.length)}
            disabled={loading}
            className="inline-flex items-center gap-1.5 font-mono text-2xs tracking-wider uppercase px-3 py-1.5 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot transition-colors disabled:opacity-50"
          >
            {loading ? <Loader2 size={11} className="animate-spin" /> : <ChevronDown size={11} />}
            Load more
          </button>
        )}
      </div>
    </Card>
  );
}
