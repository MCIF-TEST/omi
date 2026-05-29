import { cn } from '@/lib/cn';

interface LogoProps {
  className?: string;
  showName?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function Logo({ className, showName = true, size = 'md' }: LogoProps) {
  const dim = size === 'sm' ? 22 : size === 'lg' ? 36 : 28;
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <defs>
          <linearGradient id="omi-hex-stroke" x1="3" y1="2" x2="29" y2="30" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#67e8f9" />
            <stop offset="55%" stopColor="#22d3ee" />
            <stop offset="100%" stopColor="#38bdf8" />
          </linearGradient>
          <radialGradient id="omi-core-fill" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#67e8f9" stopOpacity="1" />
            <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.7" />
          </radialGradient>
          <filter id="omi-glow">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="blur" />
            <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.133  0 0 0 0 0.827  0 0 0 0 0.933  0 0 0 0.6 0" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {/* Outer hex */}
        <path
          d="M16 2.5L28.5 9.75V22.25L16 29.5L3.5 22.25V9.75L16 2.5Z"
          stroke="url(#omi-hex-stroke)"
          strokeWidth="1.25"
          fill="rgba(34, 211, 238, 0.05)"
          filter="url(#omi-glow)"
        />
        {/* Inner structure lines */}
        <path
          d="M16 2.5L16 9M16 23V29.5M3.5 9.75L9 13M23 19L28.5 22.25M28.5 9.75L23 13M9 19L3.5 22.25"
          stroke="url(#omi-hex-stroke)"
          strokeWidth="0.5"
          strokeOpacity="0.3"
        />
        {/* Core dot */}
        <circle cx="16" cy="16" r="3.5" fill="url(#omi-core-fill)" filter="url(#omi-glow)" />
      </svg>

      {showName && (
        <span
          className={cn(
            'font-mono font-bold tracking-[0.2em] text-fg',
            size === 'sm' ? 'text-xs' : size === 'lg' ? 'text-base' : 'text-sm',
          )}
        >
          OMI<span className="text-gradient">SPHERE</span>
        </span>
      )}
    </div>
  );
}
