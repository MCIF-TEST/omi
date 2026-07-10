import { type InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        // A well, not a slab: inputs sink INTO the desk (inset shadow), and the
        // brass lamp finds them on focus. Caret is brass via the global layer.
        'w-full h-10 px-3 rounded-md bg-bg-inset text-fg placeholder:text-fg-faint text-sm',
        'border border-border-2 outline-none transition-[border-color,box-shadow] duration-150',
        'shadow-[inset_0_1px_3px_rgba(0,0,0,0.35)]',
        'focus:border-accent/70 focus:ring-2 focus:ring-accent/20',
        'focus:shadow-[inset_0_1px_3px_rgba(0,0,0,0.35),0_0_14px_rgba(217,164,74,0.10)]',
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
