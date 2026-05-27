import { cn } from '@/lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'animate-pulse bg-gradient-to-r from-bg-elev via-bg-elev-2 to-bg-elev rounded-sm',
        className,
      )}
      aria-hidden
    />
  );
}
