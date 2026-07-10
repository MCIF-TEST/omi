import { cn } from '@/lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-sm bg-bg-elev',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer-sweep_1.6s_infinite]',
        // the sweep is warm lamplight passing over the surface, not gray static
        'after:bg-gradient-to-r after:from-transparent after:via-[rgba(236,194,117,0.05)] after:to-transparent',
        className,
      )}
      aria-hidden
    />
  );
}
