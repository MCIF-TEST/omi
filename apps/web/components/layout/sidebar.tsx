'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard, Search, Network, MessageSquareText,
  Activity, FileText, Settings, Folder, Database, type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/cn';

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: string;          // "soon", "beta", etc.
  disabled?: boolean;
}

const NAV: NavItem[] = [
  { href: '/dashboard',       label: 'Dashboard',     icon: LayoutDashboard },
  { href: '/investigate',     label: 'Investigate',   icon: Search },
  { href: '/investigations',  label: 'Investigations', icon: Folder },
  { href: '/graph',           label: 'Graph',         icon: Network },
  { href: '/narratives',      label: 'Narratives',    icon: MessageSquareText },
  { href: '/content',         label: 'Content DB',    icon: Database },
  { href: '/monitoring',      label: 'Monitoring',    icon: Activity },
  { href: '/settings',        label: 'Settings',      icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col border-r border-border-1 bg-bg">
      <nav className="flex-1 px-3 py-6 space-y-1">
        <div className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase px-3 mb-3">
          Workspace
        </div>
        {NAV.map((item) => {
          const active = pathname?.startsWith(item.href);
          const Icon = item.icon;
          const content = (
            <span
              className={cn(
                'flex items-center justify-between gap-3 px-3 py-2 rounded-sm transition-colors duration-150',
                active
                  ? 'bg-bg-elev text-accent border-l-2 border-accent -ml-0.5 pl-[10px]'
                  : 'text-fg-dim hover:text-fg hover:bg-bg-elev/60 border-l-2 border-transparent -ml-0.5 pl-[10px]',
                item.disabled && 'opacity-40 cursor-not-allowed',
              )}
            >
              <span className="flex items-center gap-3">
                <Icon size={16} strokeWidth={1.5} />
                <span className="text-sm">{item.label}</span>
              </span>
              {item.badge && (
                <span className="font-mono text-[10px] tracking-wider uppercase text-fg-mute border border-border-2 px-1.5 py-0.5 rounded-sm">
                  {item.badge}
                </span>
              )}
            </span>
          );
          return item.disabled ? (
            <div key={item.href} aria-disabled>
              {content}
            </div>
          ) : (
            <Link key={item.href} href={item.href}>
              {content}
            </Link>
          );
        })}
      </nav>
      <div className="px-6 py-4 border-t border-border-1 font-mono text-2xs tracking-wider text-fg-faint">
        OMISPHERE · v1
      </div>
    </aside>
  );
}
