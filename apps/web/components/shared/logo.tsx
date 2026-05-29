import { cn } from '@/lib/cn';

interface LogoProps {
  className?: string;
  showName?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function Logo({ className, showName = true, size = 'md' }: LogoProps) {
  const dim = size === 'sm' ? 24 : size === 'lg' ? 38 : 30;
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 36 36"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <defs>
          <linearGradient id="omi-stroke" x1="4" y1="3" x2="32" y2="33" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#ab9dff" />
            <stop offset="50%" stopColor="#8b7bff" />
            <stop offset="100%" stopColor="#ff7a5c" />
          </linearGradient>
          <radialGradient id="omi-core" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ab9dff" />
            <stop offset="100%" stopColor="#8b7bff" stopOpacity="0.65" />
          </radialGradient>
          <filter id="omi-glow">
            <feGaussianBlur in="SourceGraphic" stdDeviation="1.6" result="b" />
            <feColorMatrix in="b" type="matrix"
              values="0 0 0 0 0.545  0 0 0 0 0.482  0 0 0 0 1  0 0 0 0.6 0" result="g" />
            <feMerge>
              <feMergeNode in="g" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Orbital rings — the "sphere" */}
        <circle cx="18" cy="18" r="14.5" stroke="url(#omi-stroke)" strokeWidth="1.4"
          fill="rgba(139,123,255,0.04)" filter="url(#omi-glow)" />
        <ellipse cx="18" cy="18" rx="14.5" ry="6" stroke="url(#omi-stroke)" strokeWidth="0.8"
          strokeOpacity="0.45" transform="rotate(-28 18 18)" />
        <ellipse cx="18" cy="18" rx="6" ry="14.5" stroke="url(#omi-stroke)" strokeWidth="0.8"
          strokeOpacity="0.3" transform="rotate(-28 18 18)" />

        {/* Core */}
        <circle cx="18" cy="18" r="4" fill="url(#omi-core)" filter="url(#omi-glow)" />
      </svg>

      {showName && (
        <span
          className={cn(
            'display font-semibold tracking-tight text-fg',
            size === 'sm' ? 'text-sm' : size === 'lg' ? 'text-xl' : 'text-base',
          )}
        >
          omi<span className="text-brand">sphere</span>
        </span>
      )}
    </div>
  );
}
