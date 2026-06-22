import { type InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        'w-full h-10 px-3 rounded-md bg-bg-elev-2 text-fg placeholder:text-fg-mute text-sm',
        'border border-border-2 outline-none transition-colors duration-150',
        'focus:border-accent focus:ring-2 focus:ring-accent/25',
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
