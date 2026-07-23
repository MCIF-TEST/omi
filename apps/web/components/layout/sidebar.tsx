'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Search, Network, MessageSquareText, Megaphone,
  Activity, FileText, Settings, Folder, Database, type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { Logo } from '@/components/shared/logo';

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  disabled?: boolean;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Intelligence',
    items: [
      { href: '/investigate',    label: 'Investigate',   icon: Search },
      { href: '/investigations', label: 'Investigations',icon: Folder },
    ],
  },
  {
    // Coordination-first framing — Campaigns are the durable account-cluster
    // asset; Narratives are message-cluster (different grain — don't conflate);
    // Graph is the cross-scan account network. Content DB is "what was scanned",
    // not coordination output — moved to its own group below.
    label: 'Coordination',
    items: [
      { href: '/campaigns',      label: 'Campaigns',     icon: Megaphone },
      { href: '/narratives',     label: 'Narratives',    icon: MessageSquareText },
      { href: '/graph',          label: 'Graph',         icon: Network },
    ],
  },
  {
    label: 'Sources',
    items: [
      { href: '/content',        label: 'Content DB',    icon: Database },
    ],
  },
  {
    label: 'Operations',
    items: [
      { href: '/monitoring',     label: 'Monitoring',    icon: Activity },
      { href: '/settings',       label: 'Settings',      icon: Settings },
    ],
  },
];

// Pre-activation (no investigations yet) the nav narrows to the value-moment
// path: Dashboard / Investigate / Investigations / Campaigns / Settings.
const NEW_USER_VISIBLE = new Set([
  '/investigate', '/investigations', '/campaigns', '/settings',
]);

function visibleGroups(isNewUser: boolean) {
  if (!isNewUser) return NAV_GROUPS;
  return NAV_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((i) => NEW_USER_VISIBLE.has(i.href)) }))
    .filter((g) => g.items.length > 0);
}

export function Sidebar({ isNewUser = false }: { isNewUser?: boolean }) {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border-1 bg-bg-sidebar">
      {/* Brand lockup */}
      <div className="px-4 h-14 flex items-center border-b border-border-1/70">
        <Logo size="sm" />
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-4 px-2.5 space-y-6">
        {visibleGroups(isNewUser).map((group) => (
          <div key={group.label}>
            <div className="px-2.5 mb-2 select-none">
              <span className="font-mono text-[0.6rem] tracking-[0.22em] text-fg-faint uppercase">
                {group.label}
              </span>
            </div>
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const active = !!pathname?.startsWith(item.href);
                const Icon = item.icon;
                const inner = (
                  <span
                    className={cn(
                      'nav-item w-full',
                      active && 'active',
                      item.disabled && 'opacity-40 cursor-not-allowed pointer-events-none',
                    )}
                  >
                    <Icon
                      size={16}
                      strokeWidth={active ? 2.1 : 1.6}
                      className={cn(
                        'transition-colors',
                        active ? 'text-accent-2' : 'text-fg-mute group-hover:text-fg-dim',
                      )}
                    />
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span className="font-mono text-[0.55rem] tracking-wider uppercase text-fg-faint border border-border-2 px-1 py-0.5 rounded">
                        {item.badge}
                      </span>
                    )}
                  </span>
                );
                return item.disabled ? (
                  <div key={item.href} aria-disabled className="group">
                    {inner}
                  </div>
                ) : (
                  <Link key={item.href} href={item.href} className="block group">
                    {inner}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* Status footer */}
      <div className="px-4 py-3 border-t border-border-1/70 flex items-center justify-between">
        <span className="inline-flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full rounded-full bg-tier-low opacity-60 animate-ping" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-tier-low" />
          </span>
          <span className="font-mono text-[0.6rem] tracking-[0.15em] text-fg-mute uppercase">
            Engine online
          </span>
        </span>
        <span className="font-mono text-[0.6rem] tracking-[0.15em] text-fg-faint uppercase">
          v1
        </span>
      </div>
    </aside>
  );
}
