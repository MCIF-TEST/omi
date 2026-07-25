'use client';

import { useState } from 'react';
import { cn } from '@/lib/cn';

type Platform = 'youtube' | 'x' | 'unknown' | string;

/**
 * Thumbnail for a previous-investigation card.
 * YouTube → real hqdefault (or stored URL). X / unknown → branded placeholder
 * so the archive always feels visual and on-theme.
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
  const [imgFailed, setImgFailed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const showImage = Boolean(thumbnailUrl) && !imgFailed;

  const sizeCls =
    size === 'sm'
      ? 'w-[5.5rem] h-12 rounded-lg'
      : size === 'lg'
        ? 'w-full aspect-video rounded-xl'
        : 'w-full aspect-[16/9] rounded-t-xl';

  return (
    <div
      className={cn(
        'relative overflow-hidden shrink-0 isolate',
        sizeCls,
        !showImage && isX && 'bg-[#0a0e14]',
        !showImage && isYt && 'bg-gradient-to-br from-[#1a0a0a] via-bg-elev-2 to-bg-elev-3',
        !showImage && !isX && !isYt && 'bg-gradient-to-br from-bg-elev-3 to-bg-elev-2',
        className,
      )}
    >
      {showImage ? (
        <>
          {/* soft placeholder while the image loads */}
          <div
            className={cn(
              'absolute inset-0 bg-bg-elev-3 transition-opacity duration-300',
              loaded ? 'opacity-0' : 'opacity-100',
            )}
            aria-hidden
          >
            <div className="absolute inset-0 animate-pulse bg-gradient-to-r from-transparent via-fg/5 to-transparent" />
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={thumbnailUrl!}
            alt={label ? `Thumbnail for ${label}` : ''}
            className={cn(
              'absolute inset-0 h-full w-full object-cover transition-all duration-500',
              'group-hover:scale-[1.05]',
              loaded ? 'opacity-100' : 'opacity-0',
            )}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onLoad={() => setLoaded(true)}
            onError={() => setImgFailed(true)}
          />
          {/* bottom vignette for platform chip legibility */}
          <div
            className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg/75 via-bg/10 to-transparent"
            aria-hidden
          />
          {/* YouTube play cue */}
          {isYt && size !== 'sm' && (
            <span
              className={cn(
                'pointer-events-none absolute inset-0 flex items-center justify-center',
                'opacity-0 group-hover:opacity-100 transition-opacity duration-300',
              )}
              aria-hidden
            >
              <span className="flex h-11 w-11 items-center justify-center rounded-full bg-black/55 border border-white/15 backdrop-blur-sm shadow-card">
                <PlayIcon className="text-white ml-0.5" />
              </span>
            </span>
          )}
        </>
      ) : (
        <Placeholder platform={p} isX={isX} isYt={isYt} size={size} />
      )}

      <PlatformChip platform={p} className="absolute left-2 top-2 z-10" compact={size === 'sm'} />
    </div>
  );
}

function Placeholder({
  platform,
  isX,
  isYt,
  size,
}: {
  platform: string;
  isX: boolean;
  isYt: boolean;
  size: 'sm' | 'md' | 'lg';
}) {
  return (
    <div className="absolute inset-0 flex items-center justify-center" aria-hidden>
      {/* brand aurora */}
      <span
        className={cn(
          'pointer-events-none absolute -right-8 -top-8 h-28 w-28 rounded-full blur-3xl opacity-50',
          isX ? 'bg-violet/35' : isYt ? 'bg-red-500/25' : 'bg-accent/20',
        )}
      />
      <span
        className={cn(
          'pointer-events-none absolute -left-6 bottom-0 h-20 w-20 rounded-full blur-2xl opacity-40',
          isX ? 'bg-fg/15' : 'bg-violet/20',
        )}
      />
      {/* subtle grid texture */}
      <span
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)',
          backgroundSize: '18px 18px',
          color: 'var(--text-faint)',
        }}
      />
      <div className="relative flex flex-col items-center gap-2">
        <span
          className={cn(
            'flex items-center justify-center rounded-2xl border border-white/10 bg-bg/40 backdrop-blur-sm shadow-card',
            size === 'sm' ? 'h-8 w-8' : 'h-12 w-12',
          )}
        >
          {isX ? (
            <XMark className={cn('text-fg', size === 'sm' ? 'w-3.5 h-3.5' : 'w-5 h-5')} />
          ) : isYt ? (
            <YtMark className={cn('text-[#ff4d4d]', size === 'sm' ? 'w-4 h-4' : 'w-6 h-6')} />
          ) : (
            <FolderMark className={cn('text-fg-mute', size === 'sm' ? 'w-3.5 h-3.5' : 'w-5 h-5')} />
          )}
        </span>
        {size !== 'sm' && (
          <span className="font-mono text-[0.55rem] tracking-[0.22em] uppercase text-fg-mute">
            {isX ? 'X · Twitter' : isYt ? 'YouTube' : 'Scan archive'}
          </span>
        )}
      </div>
    </div>
  );
}

function PlatformChip({
  platform,
  className,
  compact,
}: {
  platform: string;
  className?: string;
  compact?: boolean;
}) {
  const p = platform.toLowerCase();
  const isX = p === 'x' || p === 'twitter';
  const isYt = p === 'youtube';
  const label = isX ? 'X' : isYt ? 'YouTube' : 'Scan';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 font-mono tracking-wider uppercase',
        'rounded-full border backdrop-blur-md shadow-sm',
        compact ? 'text-[0.5rem] px-1 py-px' : 'text-[0.55rem] px-1.5 py-0.5',
        isYt && 'border-red-500/30 bg-black/55 text-red-200',
        isX && 'border-white/15 bg-black/55 text-fg',
        !isYt && !isX && 'border-white/10 bg-bg/70 text-fg-dim',
        className,
      )}
    >
      {isYt && <YtMark className="w-2.5 h-2.5" />}
      {isX && <XMark className="w-2.5 h-2.5" />}
      {label}
    </span>
  );
}

function PlayIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" className={className} aria-hidden>
      <path d="M8 5.5v13l11-6.5L8 5.5z" />
    </svg>
  );
}

function XMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} width="16" height="16" aria-hidden>
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.253 5.622L18.244 2.25zm-1.161 17.52h1.833L7.084 4.126H5.117L17.083 19.77z" />
    </svg>
  );
}

function YtMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} width="16" height="16" aria-hidden>
      <path d="M23.5 6.2a3.05 3.05 0 0 0-2.15-2.16C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.35.54A3.05 3.05 0 0 0 .5 6.2 31.9 31.9 0 0 0 0 12a31.9 31.9 0 0 0 .5 5.8 3.05 3.05 0 0 0 2.15 2.16c1.85.54 9.35.54 9.35.54s7.5 0 9.35-.54a3.05 3.05 0 0 0 2.15-2.16A31.9 31.9 0 0 0 24 12a31.9 31.9 0 0 0-.5-5.8zM9.75 15.5v-7l6.5 3.5-6.5 3.5z" />
    </svg>
  );
}

function FolderMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" className={className} width="16" height="16" aria-hidden>
      <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2h7.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9z" />
    </svg>
  );
}
