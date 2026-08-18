import { cn } from '@/lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-sm bg-bg-elev',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-[shimmer-sweep_1.6s_infinite]',
        // A cool pass over the surface, at the same value as the hairlines.
        // This was a warm amber sweep left from a brass palette the product no
        // longer has, so every loading state briefly lit warm on a cold page.
        'after:bg-gradient-to-r after:from-transparent after:via-[rgba(148,163,184,0.07)] after:to-transparent',
        className,
      )}
      aria-hidden
    />
  );
}
