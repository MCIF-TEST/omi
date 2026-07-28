import { cn } from '@/lib/cn';

interface LogoProps {
  className?: string;
  showName?: boolean;
  size?: 'sm' | 'md' | 'lg';
  /** Render the "Online Media Intelligence" tagline beneath the wordmark. */
  tagline?: boolean;
}

export function Logo({ className, showName = true, size = 'md', tagline = false }: LogoProps) {
  const dim = size === 'sm' ? 26 : size === 'lg' ? 40 : 32;
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
        className="shrink-0"
      >
        <defs>
          {/* The identity ring. Deep blue, a single clean scan aperture. */}
          <linearGradient id="omi-ring" x1="6" y1="6" x2="34" y2="34" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#5b9dff" />
            <stop offset="100%" stopColor="#3b82f6" />
          </linearGradient>
        </defs>

        {/* Identity ring, a near-complete circle with a scan aperture (no glow). */}
        <path
          d="M31.5 10 A15 15 0 1 0 34 22.5"
          stroke="url(#omi-ring)"
          strokeWidth="2.5"
          strokeLinecap="round"
          fill="none"
        />

        {/* Node-network globe, the evidence graph. Edges in quiet blue. */}
        <g stroke="#3b82f6" strokeWidth="0.9" strokeOpacity="0.45">
          <line x1="13" y1="16" x2="22" y2="12.5" />
          <line x1="22" y1="12.5" x2="27" y2="20" />
          <line x1="27" y1="20" x2="20" y2="27.5" />
          <line x1="20" y1="27.5" x2="13" y2="16" />
          <line x1="13" y1="16" x2="27" y2="20" />
        </g>
        {/* Peripheral nodes in blue; ONE node in purple, the intelligence layer. */}
        <g>
          <circle cx="13" cy="16" r="1.35" fill="#5b9dff" />
          <circle cx="22" cy="12.5" r="1.35" fill="#7052f0" />
          <circle cx="27" cy="20" r="1.35" fill="#5b9dff" />
          <circle cx="20" cy="27.5" r="1.35" fill="#5b9dff" />
        </g>
        {/* Center hub. Solid blue. */}
        <circle cx="20" cy="20" r="2.3" fill="#3b82f6" />
      </svg>

      {showName && (
        <div className="flex flex-col leading-none">
          {/* Wordmark. Inter, tight; blue OMI + ink SPHERE. */}
          <span
            className={cn(
              'display tracking-[-0.01em] font-semibold',
              size === 'sm' ? 'text-[0.95rem]' : size === 'lg' ? 'text-[1.35rem]' : 'text-[1.1rem]',
            )}
          >
            <span className="text-gradient">OMI</span>
            <span className="text-silver">SPHERE</span>
          </span>
          {tagline && (
            <span className="font-mono text-[0.55rem] tracking-[0.28em] text-fg-mute uppercase mt-1">
              Online Media Intelligence
            </span>
          )}
        </div>
      )}
    </div>
  );
}
