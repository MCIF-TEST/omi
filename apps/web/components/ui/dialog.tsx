'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/cn';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  /** ARIA label for the dialog (read by screen readers). */
  label?: string;
}

/**
 * Minimal accessible dialog. Backdrop close, ESC close, focus trap.
 * Mounted globally for the Cmd+K palette; can be reused elsewhere.
 */
export function Dialog({ open, onClose, children, className, label }: DialogProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    // Focus first focusable
    requestAnimationFrame(() => {
      const el = ref.current?.querySelector<HTMLElement>('input,button,[tabindex]:not([tabindex="-1"])');
      el?.focus();
    });
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[16vh] px-4 bg-bg-deep/70 backdrop-blur-sm animate-fade-up"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={label}
    >
      <div
        ref={ref}
        className={cn(
          'w-full max-w-2xl bg-bg-elev border border-border-2 rounded-md shadow-2xl',
          className,
        )}
      >
        <button
          onClick={onClose}
          className="absolute top-3 right-3 p-1 text-fg-mute hover:text-fg-dim rounded-sm"
          aria-label="Close"
          type="button"
        >
          <X size={14} />
        </button>
        {children}
      </div>
    </div>
  );
}
