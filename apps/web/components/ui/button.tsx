import { type ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

/**
 * Omi Noir buttons are machined objects, not painted rectangles: light enters
 * from above (inset top edge), the base sits in shade, and a press travels a
 * real pixel while the top-light leaves the edge. Materials live in globals
 * (.btn-lamp / .btn-slab) so raw <button>s can wear them too.
 */
const variantClasses: Record<Variant, string> = {
  primary:
    'btn-lamp font-semibold disabled:cursor-not-allowed',
  secondary:
    'btn-slab text-fg disabled:opacity-50 disabled:cursor-not-allowed',
  ghost:
    'bg-transparent text-fg-dim hover:text-fg hover:bg-bg-elev active:bg-bg-elev-2 ' +
    'border border-transparent disabled:opacity-50 transition-colors duration-150',
  danger:
    'bg-tier-high/10 text-tier-high hover:bg-tier-high/20 border border-tier-high/40 ' +
    'shadow-[inset_0_1px_0_rgba(244,63,104,0.12)] active:translate-y-px ' +
    'transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed',
};

const sizeClasses: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs rounded-md',
  md: 'h-9 px-4 text-sm rounded-md',
  lg: 'h-11 px-6 text-[0.9rem] rounded-lg',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 font-medium select-none whitespace-nowrap',
        'tracking-[0.01em] ease-omi focus-visible:outline-none focus-visible:ring-2',
        'focus-visible:ring-accent/60 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-deep',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
