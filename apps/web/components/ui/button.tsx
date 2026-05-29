import { type ButtonHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantClasses: Record<Variant, string> = {
  primary:
    'bg-accent text-bg-deep hover:bg-accent-2 border border-accent btn-glow disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none disabled:before:hidden',
  secondary:
    'bg-bg-elev text-fg hover:bg-bg-elev-2 border border-border-2 hover:border-border-hot disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150',
  ghost:
    'bg-transparent text-fg-dim hover:text-fg hover:bg-bg-elev border border-transparent disabled:opacity-50 transition-colors duration-150',
  danger:
    'bg-tier-high/10 text-tier-high hover:bg-tier-high/20 border border-tier-high/40 transition-colors duration-150',
};

const sizeClasses: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs tracking-wide',
  md: 'h-10 px-4 text-sm',
  lg: 'h-12 px-6 text-sm tracking-wider font-semibold',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-sm font-medium uppercase',
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
