'use client';

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface RevealProps {
  children: ReactNode;
  /** Delay before the reveal animation, in ms. */
  delay?: number;
  /** Travel direction the element eases in from. */
  from?: 'up' | 'down' | 'left' | 'right' | 'scale';
  className?: string;
  as?: 'div' | 'section' | 'li' | 'article';
}

const OFFSCREEN: Record<NonNullable<RevealProps['from']>, string> = {
  up:    'translate-y-6',
  down:  '-translate-y-6',
  left:  'translate-x-6',
  right: '-translate-x-6',
  scale: 'scale-95',
};

/**
 * Scroll-triggered reveal. Element fades + eases in the first time it
 * enters the viewport, then stays put. Honors prefers-reduced-motion by
 * rendering visible immediately.
 */
export function Reveal({
  children,
  delay = 0,
  from = 'up',
  className,
  as: Tag = 'div',
}: RevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setShown(true);
      return;
    }
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag
      // @ts-expect-error — ref typing across the polymorphic Tag union
      ref={ref}
      style={{ transitionDelay: shown ? `${delay}ms` : '0ms' }}
      className={cn(
        'transition-all duration-700 ease-omi will-change-transform',
        shown ? 'opacity-100 translate-x-0 translate-y-0 scale-100' : cn('opacity-0', OFFSCREEN[from]),
        className,
      )}
    >
      {children}
    </Tag>
  );
}
