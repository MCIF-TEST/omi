import { type InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'w-full h-10 px-3 rounded-sm bg-bg-elev text-fg placeholder:text-fg-mute',
        'border border-border-2 focus:border-accent focus:outline-none focus:shadow-glow-sm focus:bg-bg-elev-2/60',
        'transition-all duration-200 font-mono text-sm',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';

export const Label = forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label
      ref={ref}
      className={cn(
        'block text-2xs font-mono tracking-[0.18em] text-fg-mute uppercase mb-1.5',
        className,
      )}
      {...props}
    />
  ),
);
Label.displayName = 'Label';
