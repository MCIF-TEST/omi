import { cn } from '@/lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-sm bg-bg-elev',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer-sweep_1.6s_infinite]',
        'after:bg-gradient-to-r after:from-transparent after:via-bg-elev-2 after:to-transparent',
        className,
      )}
      aria-hidden
    />
  );
}
