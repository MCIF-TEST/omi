'use client';

import { cn } from '@/lib/cn';

type Platform = 'youtube' | 'x' | 'unknown' | string;

/**
 * Thumbnail for a previous investigation card.
 * YouTube → real hqdefault (or stored URL). X / unknown → branded placeholder
 * with platform mark so the archive still feels visual and on-theme.
 */
export function InvestigationThumb({
  platform,
  thumbnailUrl,
  label,
  className,
  size = 'md',
}: {
  platform?: Platform | null;
  thumbnailUrl?: string | null;
  label?: string;
  className?: string;
  /** sm = list row, md = card grid, lg = hero */
  size?: 'sm' | 'md' | 'lg';
}) {
  const p = (platform || 'unknown').toLowerCase();
  const isYt = p === 'youtube';
  const isX = p === 'x' || p === 'twitter';
  const sizeCls =
    size === 'sm'
      ? 'w-20 h-12 rounded-md'
      : size === 'lg'
        ? 'w-full aspect-video rounded-xl'
        : 'w-full aspect-video rounded-t-xl';

  if (thumbnailUrl) {
    return (
      <div className={cn('relative overflow-hidden bg-bg-elev-3 shrink-0', sizeCls, className)}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={thumbnailUrl}
          alt={label ? `Thumbnail for ${label}` : ''}
          className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.04]"
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-bg/70 via-transparent to-transparent opacity-80" />
        <PlatformChip platform={p} className="absolute left-2 top-2" />
      </div>
    );
  }

  return (
    <div
      className={cn(
        'relative overflow-hidden shrink-0 flex items-center justify-center',
        sizeCls,
        isX && 'bg-gradient-to-br from-[#0f1419] via-bg-elev-2 to-violet-soft/30',
        isYt && 'bg-gradient-to-br from-bg-elev-3 via-bg-elev-2 to-accent/10',
        !isX && !isYt && 'bg-gradient-to-br from-bg-elev-3 to-bg-elev-2',
        className,
      )}
      aria-hidden={!label}
    >
      {/* Soft brand aurora */}
      <span
        className={cn(
          'pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full blur-2xl opacity-40',
          isX ? 'bg-violet/40' : isYt ? 'bg-accent/30' : 'bg-accent/20',
        )}
      />
      <span
        className={cn(
          'pointer-events-none absolute -left-4 bottom-0 h-16 w-16 rounded-full blur-xl opacity-30',
          isX ? 'bg-fg/20' : 'bg-violet/25',
        )}
      />
      <div className="relative flex flex-col items-center gap-1.5">
        {isX ? <XMark className="text-fg" /> : isYt ? <YtMark className="text-accent" /> : <FolderMark className="text-fg-mute" />}
        {size !== 'sm' && (
          <span className="font-mono text-[0.55rem] tracking-[0.2em] uppercase text-fg-mute">
            {isX ? 'X post' : isYt ? 'YouTube' : 'Scan'}
          </span>
        )}
      </div>
      <PlatformChip platform={p} className="absolute left-2 top-2" />
    </div>
  );
}

function PlatformChip({ platform, className }: { platform: string; className?: string }) {
  const p = platform.toLowerCase();
  const label = p === 'x' || p === 'twitter' ? 'X' : p === 'youtube' ? 'YouTube' : 'Scan';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-mono text-[0.55rem] tracking-wider uppercase',
        'px-1.5 py-0.5 rounded-full border backdrop-blur-md',
        'border-white/10 bg-bg/70 text-fg-dim',
        className,
      )}
    >
      {label}
    </span>
  );
}

function XMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" className={className} aria-hidden>
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.253 5.622L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z" />
    </svg>
  );
}

function YtMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" className={className} aria-hidden>
      <path d="M23.5 6.2a3.05 3.05 0 0 0-2.15-2.16C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.35.54A3.05 3.05 0 0 0 .5 6.2 31.9 31.9 0 0 0 0 12a31.9 31.9 0 0 0 .5 5.8 3.05 3.05 0 0 0 2.15 2.16c1.85.54 9.35.54 9.35.54s7.5 0 9.35-.54a3.05 3.05 0 0 0 2.15-2.16A31.9 31.9 0 0 0 24 12a31.9 31.9 0 0 0-.5-5.8zM9.75 15.5v-7l6.5 3.5-6.5 3.5z" />
    </svg>
  );
}

function FolderMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" className={className} aria-hidden>
      <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2h7.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9z" />
    </svg>
  );
}
