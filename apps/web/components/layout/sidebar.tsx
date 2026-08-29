'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Search, Network, Waypoints, MessageSquareText,
  Activity, Settings, History, Scale, type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { Logo } from '@/components/shared/logo';

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;
  disabled?: boolean;
  /** Admin-only. The page itself re-checks on the server; this only hides the link. */
  adminOnly?: boolean;
}

const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Intelligence',
    items: [
      { href: '/investigate',    label: 'Investigate',              icon: Search },
      { href: '/investigations', label: 'Previous investigations',  icon: History },
    ],
  },
  {
    // Graph is the cross-scan account network. The coordinated-account cluster
    // surface was removed pending a proper coordinated-events algorithm.
    label: 'Coordination',
    items: [
      { href: '/graph',          label: 'Graph',         icon: Network },
      { href: '/narratives',     label: 'Coordination',  icon: MessageSquareText, adminOnly: true },
    ],
  },
  {
    label: 'Operations',
    items: [
      { href: '/monitoring',     label: 'Monitoring',    icon: Activity },
      { href: '/disputes',       label: 'Disputes',      icon: Scale, adminOnly: true },
      { href: '/netdetect',      label: 'Formations',    icon: Waypoints, adminOnly: true },
      { href: '/settings',       label: 'Settings',      icon: Settings },
    ],
  },
];

// Pre-activation (no investigations yet) the nav narrows to the value-moment
// path: Investigate / Previous investigations / Settings.
const NEW_USER_VISIBLE = new Set([
  '/investigate', '/investigations', '/settings',
]);

function visibleGroups(isNewUser: boolean, isAdmin: boolean) {
  // Admin-only items are filtered first, so a non-admin never sees the link at all. The page
  // re-checks server-side, so hiding it here is presentation, not the access control.
  const groups = NAV_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.adminOnly || isAdmin) }))
    .filter((g) => g.items.length > 0);
  if (!isNewUser) return groups;
  return groups
    .map((g) => ({ ...g, items: g.items.filter((i) => NEW_USER_VISIBLE.has(i.href)) }))
    .filter((g) => g.items.length > 0);
}

/**
 * UTC clock for the status rack.
 *
 * Rendered only after mount, and it has to be: a clock in server-rendered HTML
 * is a hydration mismatch by construction, and the second it shows would be the
 * second the page was built rather than the second the reader is looking at.
 * The reserved width keeps the rack from reflowing when it appears.
 *
 * UTC and not local time on purpose. Every timestamp in the evidence, and every
 * arrival gap the coordination detector measures, is UTC; a console showing a
 * local clock beside UTC data invites someone to compare the two.
 */
function UtcClock() {
  const [now, setNow] = useState<string>('');
  useEffect(() => {
    const tick = () => setNow(new Date().toISOString().slice(11, 19));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="meta tabular w-[7.5ch] text-right" suppressHydrationWarning>
      {now}
    </span>
  );
}

export function Sidebar({
  isNewUser = false,
  isAdmin = false,
}: {
  isNewUser?: boolean;
  isAdmin?: boolean;
}) {
  const pathname = usePathname();
  const groups = visibleGroups(isNewUser, isAdmin);

  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border-1 bg-bg-sidebar">
      {/* Brand lockup */}
      <div className="px-4 h-14 flex items-center border-b border-border-1">
        <Logo size="sm" />
      </div>

      {/* Nav groups. Numbered, because the dossier grammar the public pages are
          built on stopped at the login boundary: the front page numbers its
          sections and the workspace, which is the part that actually IS a
          filing system, presented three unlabelled clusters of links. */}
      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-5">
        {groups.map((group, gi) => (
          <div key={group.label}>
            <div className="flex items-center gap-2 px-2 mb-1.5 select-none">
              <span className="meta tabular">{String(gi + 1).padStart(2, '0')}</span>
              <span className="h-px flex-1 bg-border-1" />
              <span className="meta">{group.label}</span>
            </div>
            <div className="space-y-px">
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
                      size={15}
                      strokeWidth={active ? 2.1 : 1.6}
                      className={cn(
                        'transition-colors shrink-0',
                        active ? 'text-accent-2' : 'text-fg-mute group-hover:text-fg-dim',
                      )}
                    />
                    <span className="flex-1 leading-snug truncate">{item.label}</span>
                    {item.badge && (
                      <span className="meta border border-border-2 px-1 rounded-sm">
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

      {/* Status rack. A steady lamp and the clock the evidence is timestamped
          in, on their own ground. The lamp used to sit inside an `animate-ping`
          halo: the softest motion in the product, on the one element meant to
          read as instrumentation. A light that is on is not animated, it is on.

          Deliberately two facts and no third. A "BUILD v1" row would fill the
          space and tell a reader nothing, and inventing chrome to look
          technical is the same instinct this product refuses on the report
          pages. */}
      <div className="border-t border-border-1 bg-bg px-3 py-2.5 flex items-center justify-between gap-2">
        <span className="inline-flex items-center gap-2 min-w-0">
          <span className="led led-ok" />
          <span className="meta meta-hi truncate">Engine online</span>
        </span>
        <UtcClock />
      </div>
    </aside>
  );
}
