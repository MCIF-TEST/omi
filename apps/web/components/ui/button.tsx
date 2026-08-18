import { type ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

/**
 * Buttons are flat and quiet: a solid fill for intent, a hairline for the rest,
 * and one real pixel of travel on press so the control feels like it heard you.
 * Primary (blue) and secondary materials live in globals (.btn-lamp / .btn-slab)
 * so raw <button>s wear them too. Transitions name exact properties, never `all`.
 */
const variantClasses: Record<Variant, string> = {
  primary:
    'btn-lamp font-semibold disabled:cursor-not-allowed',
  secondary:
    'btn-slab text-fg disabled:opacity-50 disabled:cursor-not-allowed',
  ghost:
    'bg-transparent text-fg-dim hover:text-fg hover:bg-bg-elev active:bg-bg-elev-2 ' +
    'active:translate-y-px border border-transparent disabled:opacity-50 ' +
    'transition-[color,background-color,transform] duration-150',
  danger:
    'bg-danger/10 text-danger hover:bg-danger/[0.16] border border-danger/40 ' +
    'shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] active:translate-y-px ' +
    'transition-[background-color,transform] duration-150 disabled:opacity-50 disabled:cursor-not-allowed',
};

// Console heights. `lg` came down from 44px: a 44px control is a touch target
// on a marketing page and a slab in a dense workspace, and every `lg` in this
// product sits on a desktop surface beside 34px panel headers.
// Touch reach is handled where it belongs, by the mobile tab bar and by `sm`
// controls keeping a 32px box.
const sizeClasses: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs rounded-md',
  md: 'h-9 px-4 text-sm rounded-md',
  lg: 'h-10 px-5 text-[0.875rem] rounded-md',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 font-medium select-none whitespace-nowrap',
        // Focus is a hard outline on the edge, not a ring at an offset. A 2px
        // halo held 2px away from a 3px corner reads as a glow around a square
        // object, which is the one thing the design language forbids outright.
        'tracking-[0.01em] ease-omi focus-hard focus-visible:outline-none',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
