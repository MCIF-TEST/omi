import { cn } from '@/lib/cn';

interface LogoProps {
  className?: string;
  showName?: boolean;
}

export function Logo({ className, showName = true }: LogoProps) {
  return (
    <div className={cn('inline-flex items-center gap-2.5', className)}>
      <svg
        width="28"
        height="28"
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden
      >
        <path
          d="M16 2L29 9.5V22.5L16 30L3 22.5V9.5L16 2Z"
          stroke="var(--accent)"
          strokeWidth="1.5"
          fill="rgba(34, 211, 238, 0.06)"
        />
        <circle cx="16" cy="16" r="4" fill="var(--accent)" />
      </svg>
      {showName && (
        <span className="font-mono text-sm font-bold tracking-[0.18em] text-fg">
          OMISPHERE
        </span>
      )}
    </div>
  );
}
