import { type InputHTMLAttributes, forwardRef } from 'react';
import { cn } from '@/lib/cn';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        // A well, not a slab: inputs sink INTO the surface (inset shadow) and the
        // frame goes live on focus.
        'w-full h-10 px-3 rounded-md bg-bg-inset text-fg placeholder:text-fg-faint text-sm',
        'border border-border-2 outline-none transition-[border-color] duration-150',
        'shadow-[inset_0_1px_3px_rgba(0,0,0,0.35)]',
        // Focus is the edge going live, plus a hard square outline. It used to
        // be a 2px soft ring PLUS a 14px amber halo left over from a brass
        // palette this product no longer has: a glow, in the one design
        // language that forbids glow outright, in the colour that means
        // "elevated suspicion" everywhere else on the page.
        'focus:border-accent focus-hard',
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = 'Input';

export const Label = forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label ref={ref} className={cn('meta meta-hi block mb-1.5', className)} {...props} />
  ),
);
Label.displayName = 'Label';
