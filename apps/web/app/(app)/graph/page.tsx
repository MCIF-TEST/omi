import { Network, Users } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { type AccountSubgraphResponse, type CommunitiesResponse, ApiError } from '@/lib/api';
import { apiServer } from '@/lib/api-server';
import { GraphExplorer } from './graph-explorer';

export const metadata = { title: 'Graph — OMISPHERE' };
export const dynamic = 'force-dynamic';

export default async function GraphPage({
  searchParams,
}: {
  searchParams: { focal?: string; platform?: string };
}) {
  const platform = searchParams.platform || 'youtube';
  const focal = (searchParams.focal || '').trim();

  // Always load communities (no focal needed)
  let communities: CommunitiesResponse;
  try {
    communities = await apiServer<CommunitiesResponse>(
      `/v1/graph/communities?platform=${platform}&min_size=3&limit=10`,
    );
  } catch {
    communities = { platform, min_size: 3, communities: [] };
  }

  // Subgraph only when a focal is requested
  let subgraph: AccountSubgraphResponse | null = null;
  let subgraphError: string | null = null;
  if (focal) {
    try {
      subgraph = await apiServer<AccountSubgraphResponse>(
        `/v1/graph/account/${platform}/${encodeURIComponent(focal)}?depth=2`,
      );
    } catch (e) {
      subgraphError = e instanceof ApiError ? e.message : 'Failed to load graph.';
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Coordination intelligence
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">
          Graph view
        </h1>
        <p className="mt-2 text-sm text-fg-dim max-w-2xl">
          Persistent, cross-scan coordination edges. Edges accumulate every time
          two accounts appear in the same per-scan cluster. Communities are
          detected via Louvain modularity over the whole graph.
        </p>
      </header>

      <Card>
        <CardLabel>Account subgraph</CardLabel>
        <CardTitle>Explore an account's 2-hop neighborhood</CardTitle>
        <p className="text-sm text-fg-dim mb-4">
          Enter a YouTube channel ID (starts with <span className="mono">UC…</span>) to render the
          coordination network around it. Edge thickness is coordination strength;
          node color is Louvain community; halo is the account's last scan tier.
        </p>
        <GraphExplorer initialFocal={focal} platform={platform} />
        {subgraphError && (
          <p className="mt-4 text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
            {subgraphError}
          </p>
        )}
      </Card>

      {subgraph && (
        <Card>
          <CardLabel>
            {subgraph.focal} · {subgraph.nodes.length} nodes · {subgraph.edges.length} edges
            · {subgraph.community_count} communit{subgraph.community_count === 1 ? 'y' : 'ies'}
          </CardLabel>
          <RadialGraphIsland data={subgraph} />
        </Card>
      )}

      {/* Communities overview */}
      <Card>
        <CardLabel>Detected communities · platform: {platform}</CardLabel>
        <CardTitle>
          {communities.communities.length} communit{communities.communities.length === 1 ? 'y' : 'ies'} ≥ 3 members
        </CardTitle>
        {communities.communities.length === 0 ? (
          <p className="text-sm text-fg-dim">
            No communities yet. Run more video scans — every per-scan cluster
            persists as coordination edges, and Louvain finds the dense regions
            once the graph has structure.
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
            {communities.communities.map((c) => (
              <div key={c.id} className="border border-border-1 rounded-md p-4 bg-bg">
                <div className="flex items-center justify-between mb-2">
                  <Badge variant="accent">
                    <Users size={11} /> Community #{c.id}
                  </Badge>
                  <span className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
                    {c.size} accounts
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-2xs font-mono uppercase tracking-wider text-fg-mute mb-3">
                  <div>
                    <div className="mb-0.5">Avg strength</div>
                    <div className="text-fg mono">{Math.round(c.avg_strength * 100)}%</div>
                  </div>
                  <div>
                    <div className="mb-0.5">Max strength</div>
                    <div className="text-fg mono">{Math.round(c.max_strength * 100)}%</div>
                  </div>
                </div>
                <div className="text-2xs font-mono uppercase tracking-wider text-fg-mute mb-1">
                  Methods seen
                </div>
                <div className="flex flex-wrap gap-1 mb-3">
                  {c.methods_seen.map((m) => (
                    <span
                      key={m}
                      className="px-1.5 py-0.5 text-2xs font-mono rounded-sm border border-border-2 text-fg-dim"
                    >
                      {m.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
                <div className="text-2xs font-mono uppercase tracking-wider text-fg-mute mb-1">
                  Sample accounts
                </div>
                <ul className="space-y-1">
                  {c.sample_accounts.map((s) => (
                    <li key={s.external_id} className="text-sm flex items-center justify-between gap-2">
                      <a
                        href={`/graph?focal=${encodeURIComponent(s.external_id)}&platform=${platform}`}
                        className="text-fg hover:text-accent transition-colors truncate"
                      >
                        {s.handle}
                      </a>
                      {s.tier && (
                        <span className={`font-mono text-2xs uppercase tracking-wider ${tierClass(s.tier)}`}>
                          {s.tier}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function tierClass(tier: string) {
  switch (tier) {
    case 'high': return 'text-tier-high';
    case 'elevated': return 'text-tier-elevated';
    case 'moderate': return 'text-tier-moderate';
    case 'low': return 'text-tier-low';
    default: return 'text-fg-dim';
  }
}

// Client component for the graph itself (interactive selection)
import { RadialGraphIsland } from './radial-graph-island';
