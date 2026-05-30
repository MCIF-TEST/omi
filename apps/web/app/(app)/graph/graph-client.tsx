'use client';

import { useState, useEffect, useCallback } from 'react';
import { Network, Plus, Trash2, Pencil, Check, X, Users, MousePointerClick, ArrowRight } from 'lucide-react';
import { apiClient, ApiError, type UserGraphOut, type UserGraphDetail, type UserGraphMemberOut, type Tier, type GraphNode } from '@/lib/api';
import { TierBadge } from '@/components/shared/tier-badge';
import { RadialGraph } from '@/components/viz/radial-graph';

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

type ListState =
  | { status: 'loading' }
  | { status: 'ready'; graphs: UserGraphOut[] }
  | { status: 'error'; message: string };

type DetailState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; data: UserGraphDetail }
  | { status: 'error'; message: string };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tierToScore(tier: Tier | null): number | null {
  switch (tier) {
    case 'high':     return 0.9;
    case 'elevated': return 0.7;
    case 'moderate': return 0.45;
    case 'low':      return 0.1;
    default:         return null;
  }
}

function membersToGraphNodes(members: UserGraphMemberOut[]): GraphNode[] {
  return members.map((m) => ({
    external_id: m.external_id,
    handle: m.handle || m.external_id,
    display_name: m.display_name,
    tier: m.tier,
    last_score: tierToScore(m.tier),
    community_id: 0,
  }));
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function GraphClient() {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [detail, setDetail] = useState<DetailState>({ status: 'idle' });
  const [activeId, setActiveId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const loadList = useCallback(async () => {
    try {
      const graphs = await apiClient<UserGraphOut[]>('/v1/graphs');
      setList({ status: 'ready', graphs });
    } catch (e) {
      setList({ status: 'error', message: e instanceof ApiError ? e.message : 'Failed to load graphs.' });
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);

  const loadDetail = async (id: number) => {
    setActiveId(id);
    setDetail({ status: 'loading' });
    try {
      const data = await apiClient<UserGraphDetail>(`/v1/graphs/${id}`);
      setDetail({ status: 'ready', data });
    } catch (e) {
      setDetail({ status: 'error', message: e instanceof ApiError ? e.message : 'Failed to load graph.' });
    }
  };

  const handleCreate = async () => {
    const name = newName.trim();
    if (!name) return;
    try {
      await apiClient<UserGraphOut>('/v1/graphs', {
        method: 'POST',
        body: JSON.stringify({ name, platform: 'youtube' }),
      });
      setCreating(false);
      setNewName('');
      await loadList();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Failed to create graph.');
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Delete this graph? This cannot be undone.')) return;
    try {
      await apiClient(`/v1/graphs/${id}`, { method: 'DELETE' });
      if (activeId === id) { setActiveId(null); setDetail({ status: 'idle' }); }
      await loadList();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Failed to delete graph.');
    }
  };

  const handleRename = async (id: number) => {
    const name = renameValue.trim();
    if (!name) return;
    try {
      await apiClient<UserGraphOut>(`/v1/graphs/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ name }),
      });
      setRenamingId(null);
      await loadList();
      if (activeId === id) await loadDetail(id);
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Failed to rename graph.');
    }
  };

  const handleRemoveMember = async (graphId: number, externalId: string) => {
    try {
      await apiClient(`/v1/graphs/${graphId}/members/${encodeURIComponent(externalId)}`, {
        method: 'DELETE',
      });
      await loadDetail(graphId);
      await loadList();
    } catch (e) {
      alert(e instanceof ApiError ? e.message : 'Failed to remove member.');
    }
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <header className="relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-8 md:py-7 shadow-card">
        <div className="relative flex items-start justify-between gap-4 flex-wrap">
          <div className="max-w-2xl">
            <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase mb-2 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-accent-2" />
              Coordination intelligence
            </p>
            <h1 className="display text-2xl md:text-3xl font-semibold text-fg tracking-tight">
              My Graphs
            </h1>
            <p className="mt-2.5 text-sm text-fg-dim leading-relaxed">
              Build named graphs of commenter profiles. Omi automatically draws coordination
              edges between members based on cross-scan detection data. Add profiles from
              the commenter detail panel during an investigation.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setCreating(true); setNewName(''); }}
            className="inline-flex items-center gap-1.5 h-9 px-4 rounded-sm border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 font-mono text-2xs uppercase tracking-wider transition-colors shrink-0"
          >
            <Plus size={13} /> New graph
          </button>
        </div>

        {/* Inline create form */}
        {creating && (
          <div className="relative mt-4 flex items-center gap-2">
            <input
              autoFocus
              aria-label="New graph name"
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setCreating(false); }}
              placeholder="Graph name…"
              className="flex-1 max-w-sm bg-bg border border-border-2 rounded-sm px-3 py-2 text-sm text-fg placeholder:text-fg-faint font-mono focus:outline-none focus:border-accent"
            />
            <button
              type="button"
              onClick={handleCreate}
              disabled={!newName.trim()}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-sm bg-accent text-bg font-mono text-2xs uppercase tracking-wider disabled:opacity-40"
            >
              <Check size={12} /> Create
            </button>
            <button
              type="button"
              onClick={() => setCreating(false)}
              className="inline-flex items-center h-9 px-2 rounded-sm border border-border-2 text-fg-mute hover:text-fg"
            >
              <X size={14} />
            </button>
          </div>
        )}
      </header>

      {/* Graph list */}
      {list.status === 'loading' && (
        <div className="text-center py-16 text-fg-mute font-mono text-2xs uppercase tracking-wider animate-pulse">
          Loading graphs…
        </div>
      )}

      {list.status === 'error' && (
        <p className="text-sm text-danger bg-danger/10 border border-danger/40 rounded-sm px-4 py-3 font-mono">
          {list.message}
        </p>
      )}

      {list.status === 'ready' && list.graphs.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 rounded-2xl border border-dashed border-border-2 bg-bg-elev/40">
          <div className="w-14 h-14 rounded-2xl border border-border-2 bg-bg-elev flex items-center justify-center text-fg-faint">
            <Network size={24} />
          </div>
          <div className="text-center">
            <p className="text-sm text-fg font-medium mb-1">No graphs yet</p>
            <p className="text-xs text-fg-mute max-w-[32ch]">
              Create a graph and add commenter profiles from the investigation panel.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setCreating(true); setNewName(''); }}
            className="inline-flex items-center gap-1.5 h-8 px-3 rounded-sm border border-accent/40 bg-accent/10 text-accent hover:bg-accent/20 font-mono text-2xs uppercase tracking-wider transition-colors"
          >
            <Plus size={12} /> New graph
          </button>
        </div>
      )}

      {list.status === 'ready' && list.graphs.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.graphs.map((g) => (
            <GraphCard
              key={g.id}
              graph={g}
              active={activeId === g.id}
              renaming={renamingId === g.id}
              renameValue={renamingId === g.id ? renameValue : ''}
              onSelect={() => loadDetail(g.id)}
              onDelete={() => handleDelete(g.id)}
              onStartRename={() => { setRenamingId(g.id); setRenameValue(g.name); }}
              onRenameChange={(v) => setRenameValue(v)}
              onRenameSubmit={() => handleRename(g.id)}
              onRenameCancel={() => setRenamingId(null)}
            />
          ))}
        </div>
      )}

      {/* Detail panel */}
      {activeId !== null && (
        <GraphDetailPanel
          state={detail}
          onRemoveMember={(extId) => handleRemoveMember(activeId, extId)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Graph card
// ---------------------------------------------------------------------------

function GraphCard({
  graph, active, renaming, renameValue,
  onSelect, onDelete, onStartRename, onRenameChange, onRenameSubmit, onRenameCancel,
}: {
  graph: UserGraphOut;
  active: boolean;
  renaming: boolean;
  renameValue: string;
  onSelect: () => void;
  onDelete: () => void;
  onStartRename: () => void;
  onRenameChange: (v: string) => void;
  onRenameSubmit: () => void;
  onRenameCancel: () => void;
}) {
  return (
    <div
      className={`relative rounded-2xl border p-4 transition-all cursor-pointer group ${
        active
          ? 'border-accent/50 bg-accent/[0.05] shadow-sm'
          : 'border-border-1 bg-bg-elev hover:border-border-hot'
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2 mb-3">
        {renaming ? (
          <input
            autoFocus
            aria-label="Rename graph"
            type="text"
            value={renameValue}
            onChange={(e) => onRenameChange(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === 'Enter') onRenameSubmit();
              if (e.key === 'Escape') onRenameCancel();
            }}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 bg-bg border border-accent/40 rounded-sm px-2 py-1 text-sm text-fg font-mono focus:outline-none focus:border-accent"
          />
        ) : (
          <h3 className="text-sm font-semibold text-fg truncate flex-1">{graph.name}</h3>
        )}

        <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          {renaming ? (
            <>
              <button type="button" aria-label="Save graph name" onClick={onRenameSubmit} className="p-1 rounded hover:bg-bg-elev-2 text-accent"><Check size={12} /></button>
              <button type="button" aria-label="Cancel rename" onClick={onRenameCancel} className="p-1 rounded hover:bg-bg-elev-2 text-fg-mute"><X size={12} /></button>
            </>
          ) : (
            <>
              <button type="button" onClick={onStartRename} title="Rename" className="p-1 rounded hover:bg-bg-elev-2 text-fg-mute hover:text-fg"><Pencil size={12} /></button>
              <button type="button" onClick={onDelete} title="Delete" className="p-1 rounded hover:bg-bg-elev-2 text-fg-mute hover:text-danger"><Trash2 size={12} /></button>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 font-mono text-2xs text-fg-mute uppercase tracking-wider">
        <span className="flex items-center gap-1"><Users size={11} /> {graph.member_count} member{graph.member_count !== 1 ? 's' : ''}</span>
        <span className="px-1.5 py-0.5 rounded-sm border border-border-2 text-fg-faint">{graph.platform}</span>
      </div>

      {active && (
        <div className="absolute bottom-3 right-4 font-mono text-2xs text-accent uppercase tracking-wider">viewing →</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Graph detail panel
// ---------------------------------------------------------------------------

function GraphDetailPanel({
  state,
  onRemoveMember,
}: {
  state: DetailState;
  onRemoveMember: (externalId: string) => void;
}) {
  const [selected, setSelected] = useState<UserGraphMemberOut | null>(null);

  if (state.status === 'loading') {
    return (
      <div className="text-center py-16 text-fg-mute font-mono text-2xs uppercase tracking-wider animate-pulse rounded-2xl border border-border-1">
        Loading graph…
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <p className="text-sm text-danger bg-danger/10 border border-danger/40 rounded-sm px-4 py-3 font-mono">
        {state.message}
      </p>
    );
  }

  if (state.status !== 'ready') return null;

  const { data } = state;
  const nodes = membersToGraphNodes(data.members);
  const focal = data.members[0]?.external_id ?? '';

  return (
    <div className="space-y-4">
      {/* Section label */}
      <div className="flex items-center gap-2 font-mono text-2xs tracking-[0.2em] text-accent uppercase">
        <Network size={12} />
        {data.name} — {data.member_count} member{data.member_count !== 1 ? 's' : ''} · {data.edges.length} coordination edge{data.edges.length !== 1 ? 's' : ''}
      </div>

      {data.members.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-3 py-16 rounded-2xl border border-dashed border-border-2 bg-bg-elev/40">
          <p className="text-sm text-fg-mute">
            No members yet. Add profiles from the commenter detail panel.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
          {/* Network visualization */}
          <RadialGraph
            focal={focal}
            nodes={nodes}
            edges={data.edges}
            onSelect={(n) => {
              const m = data.members.find((m) => m.external_id === n.external_id) ?? null;
              setSelected(m);
            }}
          />

          {/* Members list / selected node detail */}
          <div className="space-y-3">
            {selected ? (
              <div className="rounded-2xl border border-border-1 bg-bg-elev p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-mono text-2xs tracking-[0.2em] text-accent-2 uppercase">Selected</p>
                  <button
                    type="button"
                    onClick={() => setSelected(null)}
                    className="text-fg-mute hover:text-fg"
                  >
                    <X size={13} />
                  </button>
                </div>
                <div>
                  <p className="text-sm font-semibold text-fg">{selected.handle || selected.external_id}</p>
                  {selected.display_name && <p className="text-xs text-fg-dim">{selected.display_name}</p>}
                  {selected.tier && <div className="mt-1.5"><TierBadge tier={selected.tier as Tier} size="sm" /></div>}
                  <p className="font-mono text-2xs text-fg-faint mt-1 break-all">{selected.external_id}</p>
                </div>
                <div className="flex gap-2">
                  <a
                    href={`/accounts/${encodeURIComponent(selected.external_id)}?platform=${selected.platform}`}
                    className="flex-1 inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-sm border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot font-mono text-2xs uppercase tracking-wider transition-colors"
                  >
                    View profile <ArrowRight size={11} />
                  </a>
                  <button
                    type="button"
                    onClick={() => { onRemoveMember(selected.external_id); setSelected(null); }}
                    className="inline-flex items-center h-8 px-2 rounded-sm border border-border-2 text-fg-mute hover:text-danger hover:border-danger/40 transition-colors"
                    title="Remove from graph"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-border-1 bg-bg-elev p-4">
                <div className="flex flex-col items-center justify-center gap-3 py-6 text-center">
                  <MousePointerClick size={20} className="text-fg-faint" />
                  <p className="text-xs text-fg-mute max-w-[22ch]">Click a node to inspect the profile.</p>
                </div>
              </div>
            )}

            {/* Member list */}
            <div className="rounded-2xl border border-border-1 bg-bg-elev overflow-hidden">
              <div className="px-4 py-2 border-b border-border-1">
                <p className="font-mono text-2xs tracking-wider uppercase text-fg-mute">Members</p>
              </div>
              <ul className="divide-y divide-border-1 max-h-64 overflow-y-auto">
                {data.members.map((m) => (
                  <li
                    key={m.external_id}
                    className="flex items-center justify-between gap-2 px-4 py-2 hover:bg-bg-elev-2 cursor-pointer group"
                    onClick={() => setSelected(m)}
                  >
                    <div className="min-w-0">
                      <p className="text-sm text-fg truncate">{m.handle || m.external_id}</p>
                      {m.tier && (
                        <span className={`font-mono text-2xs uppercase tracking-wider ${tierClass(m.tier)}`}>
                          {m.tier}
                        </span>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); onRemoveMember(m.external_id); }}
                      className="opacity-0 group-hover:opacity-100 text-fg-faint hover:text-danger transition-all p-1 rounded"
                      title="Remove"
                    >
                      <Trash2 size={12} />
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function tierClass(tier: string) {
  switch (tier) {
    case 'high':     return 'text-tier-high';
    case 'elevated': return 'text-tier-elevated';
    case 'moderate': return 'text-tier-moderate';
    case 'low':      return 'text-tier-low';
    default:         return 'text-fg-dim';
  }
}
