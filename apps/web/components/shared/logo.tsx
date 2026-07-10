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
          {/* THE THERMAL SWEEP — the brand arc IS the suspicion spectrum (low→high),
              sweeping the sphere like a scan. */}
          <linearGradient id="omi-sweep" x1="6" y1="4" x2="34" y2="36" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#2ecf96" />
            <stop offset="38%" stopColor="#f2bc2e" />
            <stop offset="68%" stopColor="#f8763a" />
            <stop offset="100%" stopColor="#f43f68" />
          </linearGradient>
          {/* Brass — the investigator's lamp: network + center hub */}
          <linearGradient id="omi-brass" x1="10" y1="10" x2="30" y2="30" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#f2d492" />
            <stop offset="100%" stopColor="#d9a44a" />
          </linearGradient>
          <radialGradient id="omi-globe" cx="42%" cy="38%" r="62%">
            <stop offset="0%" stopColor="#241d13" stopOpacity="0.92" />
            <stop offset="100%" stopColor="#0a0806" stopOpacity="0.92" />
          </radialGradient>
          <filter id="omi-glow2">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.4" result="b" />
            <feColorMatrix in="b" type="matrix"
              values="0 0 0 0 0.851  0 0 0 0 0.643  0 0 0 0 0.290  0 0 0 0.7 0" result="g" />
            <feMerge><feMergeNode in="g" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* The thermal ring — the brand's signature arc */}
        <path
          d="M30 7.5 A15 15 0 1 0 32.5 28"
          stroke="url(#omi-sweep)"
          strokeWidth="3"
          strokeLinecap="round"
          fill="none"
          filter="url(#omi-glow2)"
        />

        {/* Node-network globe — brass evidence graph in the dark room */}
        <circle cx="20" cy="20" r="11" fill="url(#omi-globe)" />
        <g stroke="url(#omi-brass)" strokeWidth="0.7" strokeOpacity="0.6">
          <line x1="13" y1="16" x2="22" y2="13" />
          <line x1="22" y1="13" x2="27" y2="20" />
          <line x1="27" y1="20" x2="20" y2="27" />
          <line x1="20" y1="27" x2="13" y2="16" />
          <line x1="13" y1="16" x2="27" y2="20" />
        </g>
        <g fill="#ecc275">
          <circle cx="13" cy="16" r="1.3" />
          <circle cx="22" cy="13" r="1.3" />
          <circle cx="27" cy="20" r="1.3" />
          <circle cx="20" cy="27" r="1.3" />
        </g>
        <circle cx="20" cy="20" r="2.2" fill="url(#omi-brass)" filter="url(#omi-glow2)" />
      </svg>

      {showName && (
        <div className="flex flex-col leading-none">
          {/* Masthead wordmark — dossier serif, brass OMI + parchment SPHERE */}
          <span
            className={cn(
              'display tracking-[0.02em]',
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
