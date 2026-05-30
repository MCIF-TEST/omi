'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard, Search, Network, Bell, Menu,
  Folder, MessageSquareText, Database, Settings, LogOut, X,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { Logo } from '@/components/shared/logo';
import { apiClient, type AlertsResponse } from '@/lib/api';
import { usePolling } from '@/lib/use-polling';

interface Tab {
  href: string;
  label: string;
  icon: LucideIcon;
}

/** Boundary-aware active match so /investigations doesn't light up the
 *  /investigate tab (and vice versa). Matches the route and its subroutes. */
const routeActive = (pathname: string, href: string) =>
  pathname === href || pathname.startsWith(href + '/');

// Five thumb-reachable primaries, chosen by how often they're actually
// used: land, scan, return to your saved work, watch for alerts. Everything
// else lives in the More sheet, so nothing is more than two taps away.
const TABS: Tab[] = [
  { href: '/dashboard',      label: 'Home',       icon: LayoutDashboard },
  { href: '/investigate',    label: 'Investigate', icon: Search },
  { href: '/investigations', label: 'Saved',       icon: Folder },
  { href: '/monitoring',     label: 'Alerts',      icon: Bell },
];

const MORE_LINKS: { href: string; label: string; icon: LucideIcon; desc: string }[] = [
  { href: '/graph',      label: 'Graph',      icon: Network,           desc: 'Coordination network graphs' },
  { href: '/narratives', label: 'Narratives', icon: MessageSquareText, desc: 'Cross-scan narrative clusters' },
  { href: '/content',    label: 'Content DB', icon: Database,          desc: 'Every scanned video' },
  { href: '/search',     label: 'Search',     icon: Search,            desc: 'Find any account or channel' },
  { href: '/settings',   label: 'Settings',   icon: Settings,          desc: 'Account, billing & alerts' },
];

export function MobileNav({ email }: { email: string }) {
  const pathname = usePathname() || '';
  const router = useRouter();
  const [sheetOpen, setSheetOpen] = useState(false);

  // Unread alert count for the Alerts tab badge — same source as the topbar.
  const alerts = usePolling<AlertsResponse>(
    useCallback(() => apiClient<AlertsResponse>('/v1/monitoring/alerts?unread=true&limit=1'), []),
    60_000,
  );
  const unread = alerts.data?.unread_count ?? 0;

  // Close the sheet on navigation + lock body scroll while it's open.
  useEffect(() => { setSheetOpen(false); }, [pathname]);
  useEffect(() => {
    if (!sheetOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [sheetOpen]);

  const isActive = (t: Tab) => routeActive(pathname, t.href);
  const moreActive = MORE_LINKS.some((l) => routeActive(pathname, l.href));

  const onLogout = async () => {
    try { await apiClient('/v1/auth/logout', { method: 'POST' }); } catch { /* ignore */ }
    router.refresh();
    router.push('/login');
  };

  return (
    <>
      {/* Bottom tab bar */}
      <nav
        className="md:hidden fixed bottom-0 inset-x-0 z-40 border-t border-border-1 bg-bg/85 backdrop-blur-xl supports-[backdrop-filter]:bg-bg/70 safe-bottom"
        aria-label="Primary"
      >
        <div className="flex items-stretch px-1">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = isActive(t);
            return (
              <Link
                key={t.href}
                href={t.href}
                className={cn('tabbar-item', active && 'active')}
                aria-current={active ? 'page' : undefined}
              >
                <span className="relative">
                  <Icon size={21} strokeWidth={active ? 2.2 : 1.7} />
                  {t.href === '/monitoring' && unread > 0 && (
                    <span className="absolute -top-1.5 -right-2 min-w-[15px] h-[15px] px-1 rounded-full bg-danger text-white text-[9px] leading-[15px] text-center font-mono">
                      {unread > 99 ? '99+' : unread}
                    </span>
                  )}
                </span>
                <span>{t.label}</span>
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setSheetOpen(true)}
            className={cn('tabbar-item', moreActive && 'active')}
            aria-haspopup="dialog"
            aria-expanded={sheetOpen}
          >
            <Menu size={21} strokeWidth={moreActive ? 2.2 : 1.7} />
            <span>More</span>
          </button>
        </div>
      </nav>

      {/* More sheet */}
      {sheetOpen && (
        <div className="md:hidden fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label="More">
          <div
            className="sheet-scrim absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setSheetOpen(false)}
          />
          <div className="sheet-panel absolute inset-x-0 bottom-0 bg-bg-elev border-t border-border-1 rounded-t-2xl shadow-card-lg safe-bottom">
            {/* Grabber + header */}
            <div className="flex flex-col items-center pt-2.5 pb-1">
              <span className="w-9 h-1 rounded-full bg-border-2" aria-hidden />
            </div>
            <div className="flex items-center justify-between px-5 pt-1 pb-3">
              <Logo size="sm" />
              <button
                type="button"
                onClick={() => setSheetOpen(false)}
                className="tap inline-flex items-center justify-center w-9 h-9 -mr-2 rounded-full text-fg-mute hover:text-fg"
                aria-label="Close menu"
              >
                <X size={18} />
              </button>
            </div>

            <div className="px-3 pb-2">
              {MORE_LINKS.map((l) => {
                const Icon = l.icon;
                const active = routeActive(pathname, l.href);
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    className={cn(
                      'tap flex items-center gap-3.5 px-3 py-3 rounded-xl transition-colors',
                      active ? 'bg-accent/10' : 'active:bg-bg-elev-2',
                    )}
                  >
                    <span className={cn(
                      'flex items-center justify-center w-9 h-9 rounded-lg shrink-0',
                      active ? 'bg-accent/15 text-accent' : 'bg-bg-elev-2 text-fg-dim',
                    )}>
                      <Icon size={17} />
                    </span>
                    <span className="min-w-0">
                      <span className={cn('block text-[0.95rem] font-medium', active ? 'text-accent' : 'text-fg')}>
                        {l.label}
                      </span>
                      <span className="block text-xs text-fg-mute truncate">{l.desc}</span>
                    </span>
                  </Link>
                );
              })}
            </div>

            {/* Account */}
            <div className="border-t border-border-1 px-5 py-3 flex items-center justify-between gap-3">
              <span className="min-w-0">
                <span className="block font-mono text-2xs text-fg-mute uppercase tracking-wider">Signed in</span>
                <span className="block text-sm text-fg-dim truncate">{email}</span>
              </span>
              <button
                type="button"
                onClick={onLogout}
                className="tap inline-flex items-center gap-1.5 h-9 px-3 rounded-lg border border-border-2 text-fg-dim hover:text-fg hover:border-border-hot font-mono text-2xs uppercase tracking-wider"
              >
                <LogOut size={13} /> Log out
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
