'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Search, Network, MessageSquareText,
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
      { href: '/dashboard',      label: 'Dashboard',     icon: LayoutDashboard },
      { href: '/investigate',    label: 'Investigate',   icon: Search },
      { href: '/investigations', label: 'Investigations',icon: Folder },
    ],
  },
  {
    label: 'Analysis',
    items: [
      { href: '/graph',          label: 'Graph',         icon: Network },
      { href: '/narratives',     label: 'Narratives',    icon: MessageSquareText },
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

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden md:flex w-56 shrink-0 flex-col border-r border-border-1 bg-bg">
      {/* Logo */}
      <div className="px-4 py-5 border-b border-border-1/60">
        <Logo size="sm" />
      </div>

      {/* Nav groups */}
      <nav className="flex-1 overflow-y-auto py-4 px-2 space-y-5">
        {NAV_GROUPS.map((group) => (
          <div key={group.label}>
            <div className="px-3 mb-1.5 font-mono text-[0.6rem] tracking-[0.2em] text-fg-faint uppercase select-none">
              {group.label}
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
                      size={15}
                      strokeWidth={active ? 2 : 1.5}
                      className={active ? 'text-accent' : 'text-fg-mute group-hover:text-fg-dim'}
                    />
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span className="font-mono text-[0.55rem] tracking-wider uppercase text-fg-faint border border-border-2 px-1 py-0.5 rounded-sm">
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

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border-1/60">
        <div className="font-mono text-[0.6rem] tracking-[0.15em] text-fg-faint uppercase">
          v1 · beta
        </div>
      </div>
    </aside>
  );
}
