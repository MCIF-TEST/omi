'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Search, LayoutDashboard, MessageSquareText, Network, Settings,
  FileSearch, ArrowRight,
} from 'lucide-react';
import { Dialog } from '@/components/ui/dialog';
import { apiClient, type InvestigationsListResponse } from '@/lib/api';
import { cn } from '@/lib/cn';
import { timeAgo } from '@/lib/format';

interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  href?: string;
  action?: () => void;
  icon: React.ReactNode;
  group: string;
}

const NAV_ITEMS: PaletteItem[] = [
  { id: 'nav-dashboard',    label: 'Dashboard',   icon: <LayoutDashboard size={14} />, href: '/dashboard',  group: 'Navigate' },
  { id: 'nav-investigate',  label: 'New scan',    icon: <Search size={14} />,           href: '/investigate', group: 'Navigate', hint: 'Paste a URL to begin' },
  { id: 'nav-narratives',   label: 'Narratives',  icon: <MessageSquareText size={14} />, href: '/narratives',  group: 'Navigate' },
  { id: 'nav-graph',        label: 'Graph',       icon: <Network size={14} />,          href: '/graph',       group: 'Navigate' },
  { id: 'nav-settings',     label: 'Settings',    icon: <Settings size={14} />,         href: '/settings',    group: 'Navigate' },
];

/**
 * Global Cmd+K palette. Listens for Cmd/Ctrl+K, opens a modal with:
 *   - Recent investigations (fetched on open)
 *   - Static nav items
 * Arrow keys navigate, Enter activates.
 */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [investigations, setInvestigations] = useState<InvestigationsListResponse | null>(null);
  const [active, setActive] = useState(0);

  // Global keybind: Cmd+K / Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Fetch recent investigations when opening
  useEffect(() => {
    if (!open) return;
    setQ('');
    setActive(0);
    apiClient<InvestigationsListResponse>('/v1/investigations?limit=20')
      .then(setInvestigations)
      .catch(() => setInvestigations({ investigations: [] }));
  }, [open]);

  const items = useMemo<PaletteItem[]>(() => {
    const invItems: PaletteItem[] = (investigations?.investigations || []).map((inv) => ({
      id: `inv-${inv.slug}`,
      label: inv.label,
      hint: `${Math.round(inv.overall_probability * 100)}% · ${inv.overall_tier} · ${timeAgo(inv.created_at)}`,
      href: `/investigations/${inv.slug}`,
      icon: <FileSearch size={14} />,
      group: 'Recent investigations',
    }));
    const all = [...invItems, ...NAV_ITEMS];
    if (!q.trim()) return all;
    const needle = q.toLowerCase();
    return all.filter(
      (i) => i.label.toLowerCase().includes(needle) || (i.hint?.toLowerCase().includes(needle) ?? false),
    );
  }, [investigations, q]);

  const activate = useCallback(
    (item: PaletteItem) => {
      setOpen(false);
      if (item.href) router.push(item.href);
      item.action?.();
    },
    [router],
  );

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(items.length - 1, a + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (items[active]) activate(items[active]);
    }
  };

  return (
    <Dialog open={open} onClose={() => setOpen(false)} label="Command palette">
      <div className="p-3 border-b border-border-1">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-fg-mute" />
          <input
            aria-label="Search investigations and pages"
            value={q}
            onChange={(e) => { setQ(e.target.value); setActive(0); }}
            onKeyDown={onKey}
            placeholder="Search investigations, jump to a page…"
            className="w-full h-10 pl-9 pr-3 bg-transparent text-fg placeholder:text-fg-mute font-mono text-sm focus:outline-none"
          />
        </div>
      </div>
      <div className="max-h-[55vh] overflow-y-auto py-2">
        {items.length === 0 && (
          <div className="px-4 py-8 text-center text-fg-mute font-mono text-2xs uppercase tracking-wider">
            No matches.
          </div>
        )}
        {groupItems(items).map((g) => (
          <div key={g.group} className="mb-2">
            <div className="px-4 py-1 font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
              {g.group}
            </div>
            {g.items.map((item) => {
              const idx = items.indexOf(item);
              const isActive = idx === active;
              return (
                <button
                  key={item.id}
                  onMouseEnter={() => setActive(idx)}
                  onClick={() => activate(item)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-2 text-left transition-colors',
                    isActive ? 'bg-accent/10 text-fg' : 'text-fg-dim hover:text-fg',
                  )}
                >
                  <span className={isActive ? 'text-accent' : 'text-fg-mute'}>{item.icon}</span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm truncate">{item.label}</span>
                    {item.hint && (
                      <span className="block font-mono text-2xs text-fg-mute uppercase tracking-wider">
                        {item.hint}
                      </span>
                    )}
                  </span>
                  {isActive && <ArrowRight size={12} className="text-accent" />}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <div className="border-t border-border-1 px-4 py-2 flex items-center justify-between font-mono text-2xs uppercase tracking-wider text-fg-mute">
        <span>↑↓ navigate · ↵ open · esc close</span>
        <span className="text-accent">⌘K</span>
      </div>
    </Dialog>
  );
}

function groupItems(items: PaletteItem[]) {
  const map: Record<string, PaletteItem[]> = {};
  for (const i of items) (map[i.group] ||= []).push(i);
  return Object.entries(map).map(([group, items]) => ({ group, items }));
}
