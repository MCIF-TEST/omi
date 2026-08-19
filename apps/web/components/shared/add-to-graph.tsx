'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Loader2, Network, Plus, X } from 'lucide-react';
import { apiClient, ApiError, type Tier, type UserGraphOut } from '@/lib/api';
import {
  graphsAcceptingPlatform, isAddable, memberPayload, platformLabel,
} from '@/lib/graph-membership';
import { cn } from '@/lib/cn';

/**
 * Put one scanned account into one of the operator's named graphs, from wherever they are looking
 * at it.
 *
 * Both `/v1/graphs`'s own docstring and the `/graph` page's lede have promised this ("add profiles
 * from the commenter detail panel during an investigation") since the API shipped. The endpoints
 * were all there; the control was not, so the only way to build a graph was to already know an
 * account's external id and add it by hand.
 *
 * ONE FETCH PER PAGE, NOT ONE PER ROW. An investigation renders up to 150 of these and the graph
 * list is the same answer for every one of them, so the list is fetched once into a module-level
 * cache and shared. Without that, opening the first picker on a 100-account scan would be fine and
 * the page would still have made 100 identical requests as each control mounted.
 */

// ── the shared graph list ───────────────────────────────────────────────────────────────────────
let _cache: UserGraphOut[] | null = null;
let _inflight: Promise<UserGraphOut[]> | null = null;
const _subscribers = new Set<(g: UserGraphOut[]) => void>();

function _publish(graphs: UserGraphOut[]) {
  _cache = graphs;
  _subscribers.forEach((fn) => fn(graphs));
}

async function loadGraphs(force = false): Promise<UserGraphOut[]> {
  if (!force && _cache) return _cache;
  if (!force && _inflight) return _inflight;
  _inflight = apiClient<UserGraphOut[]>('/v1/graphs')
    .then((g) => { _publish(g); return g; })
    .finally(() => { _inflight = null; });
  return _inflight;
}

/** Every open picker re-renders when one of them creates a graph or adds a member. */
function useGraphs(): [UserGraphOut[] | null, (force?: boolean) => Promise<UserGraphOut[]>] {
  const [graphs, setGraphs] = useState<UserGraphOut[] | null>(_cache);
  useEffect(() => {
    _subscribers.add(setGraphs);
    return () => { _subscribers.delete(setGraphs); };
  }, []);
  return [graphs, loadGraphs];
}

/** Test seam + a way for a page to drop the cache when it knows it is stale. */
export function resetGraphCacheForTests(): void {
  _cache = null;
  _inflight = null;
}

// ── the control ─────────────────────────────────────────────────────────────────────────────────
export function AddToGraph({
  externalId,
  handle,
  tier,
  platform,
  className,
}: {
  externalId?: string;
  handle?: string;
  tier?: Tier | null;
  /** The INVESTIGATION's platform, not the graph's. See `graphsAcceptingPlatform`. */
  platform?: string | null;
  className?: string;
}) {
  const account = { external_id: externalId, handle, suspicion_tier: tier ?? null };
  const addable = isAddable(account, platform);

  const [open, setOpen] = useState(false);
  const [graphs, refresh] = useGraphs();
  const [busy, setBusy] = useState<number | 'new' | null>(null);
  const [addedTo, setAddedTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);

  // Close on an outside click or Escape. A popover that can only be dismissed by completing it is a
  // trap, and this one sits inside a long scrolling list where a stray open is easy.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const openPicker = useCallback(() => {
    setOpen((v) => !v);
    setError(null);
    if (!graphs) void refresh().catch(() => setError('Could not load your graphs.'));
  }, [graphs, refresh]);

  const eligible = graphsAcceptingPlatform(graphs ?? [], platform);

  const add = async (graph: UserGraphOut) => {
    setBusy(graph.id);
    setError(null);
    try {
      await apiClient(`/v1/graphs/${graph.id}/members`, {
        method: 'POST',
        body: JSON.stringify(memberPayload(account)),
      });
      setAddedTo(graph.name);
      setOpen(false);
      // The member count on every other open picker is now stale.
      void refresh(true).catch(() => { /* the count is cosmetic; the add succeeded */ });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not add this account.');
    } finally {
      setBusy(null);
    }
  };

  const createAndAdd = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy('new');
    setError(null);
    try {
      const graph = await apiClient<UserGraphOut>('/v1/graphs', {
        method: 'POST',
        // The account's own platform, so the graph it lands in can actually draw its edges.
        body: JSON.stringify({ name, platform: platform === 'twitter' ? 'x' : platform }),
      });
      await add(graph);
      setCreating(false);
      setNewName('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create the graph.');
      setBusy(null);
    }
  };

  if (!addable) return null;

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        type="button"
        onClick={openPicker}
        aria-expanded={open}
        aria-haspopup="menu"
        title={addedTo ? `Added to ${addedTo}` : 'Add this account to one of your graphs'}
        className={cn(
          'btn-slab h-7 px-2 rounded-sm inline-flex items-center gap-1.5 meta meta-on',
          addedTo && 'text-tier-low border-tier-low/40',
        )}
      >
        {addedTo ? <Check size={11} /> : <Network size={11} />}
        <span className="hidden sm:inline">{addedTo ? 'In graph' : 'Graph'}</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-1 w-64 rounded-sm border border-border-2 bg-bg-elev
                     shadow-overlay p-2"
        >
          <div className="flex items-center justify-between gap-2 px-1 pb-1.5">
            <span className="meta meta-hi">Add to graph</span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="text-fg-mute hover:text-fg"
            >
              <X size={11} />
            </button>
          </div>

          {graphs === null ? (
            <p className="meta px-1 py-2 inline-flex items-center gap-2">
              <span className="led led-work" /> Loading
            </p>
          ) : (
            <>
              {eligible.length > 0 && (
                <ul className="max-h-56 overflow-y-auto -mx-1">
                  {eligible.map((g) => (
                    <li key={g.id}>
                      <button
                        type="button"
                        role="menuitem"
                        disabled={busy !== null}
                        onClick={() => void add(g)}
                        className="w-full flex items-center gap-2 px-2 py-1.5 rounded-sm text-left
                                   hover:bg-bg-elev-2 disabled:opacity-50 group"
                      >
                        <span className="text-sm text-fg-dim group-hover:text-fg truncate flex-1 min-w-0">
                          {g.name}
                        </span>
                        <span className="meta tabular shrink-0">{g.member_count}</span>
                        {busy === g.id && <Loader2 size={11} className="animate-spin shrink-0" />}
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {eligible.length === 0 && !creating && (
                // Says WHY there is nothing to pick. "No graphs" would be wrong when the operator has
                // several and none of them are on this account's platform.
                <p className="text-2xs text-fg-mute leading-relaxed px-1 py-1.5">
                  {(graphs.length > 0)
                    ? `None of your graphs are ${platformLabel(platform)} graphs. A graph only draws edges between accounts on its own platform.`
                    : 'You have no graphs yet.'}
                </p>
              )}

              {creating ? (
                <div className="flex items-center gap-1.5 pt-1.5 mt-1.5 border-t border-border-1">
                  <input
                    autoFocus
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void createAndAdd();
                      if (e.key === 'Escape') { setCreating(false); setNewName(''); }
                    }}
                    placeholder={`New ${platformLabel(platform)} graph`}
                    aria-label="New graph name"
                    className="flex-1 min-w-0 h-8 px-2 rounded-sm bg-bg-inset border border-border-2
                               text-sm text-fg placeholder:text-fg-faint font-mono focus:border-accent focus-hard"
                  />
                  <button
                    type="button"
                    onClick={() => void createAndAdd()}
                    disabled={!newName.trim() || busy !== null}
                    className="btn-lamp h-8 px-2.5 rounded-sm inline-flex items-center gap-1 meta disabled:opacity-40"
                  >
                    {busy === 'new' ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setCreating(true)}
                  className="w-full flex items-center gap-2 px-2 py-1.5 mt-1 rounded-sm text-left
                             border-t border-border-1 pt-2 hover:bg-bg-elev-2 text-accent-text"
                >
                  <Plus size={11} />
                  <span className="meta text-accent-text">New graph</span>
                </button>
              )}

              {error && <p className="text-2xs text-danger px-1 pt-1.5 leading-relaxed">{error}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
