'use client';

import { useEffect, useRef, useState } from 'react';

interface AnimatedNumberProps {
  value: number;
  /** Animation duration in ms. */
  duration?: number;
  /** Render with thousands separators. */
  format?: boolean;
  className?: string;
  /** Start the count only when scrolled into view. */
  onView?: boolean;
}

/**
 * Counts up to `value` with an ease-out curve — a small dopamine hit on
 * every stat. Respects prefers-reduced-motion (jumps straight to value)
 * and can defer until scrolled into view.
 */
export function AnimatedNumber({
  value,
  duration = 1100,
  format = true,
  className,
  onView = false,
}: AnimatedNumberProps) {
  const [display, setDisplay] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  const started = useRef(false);

  useEffect(() => {
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    if (reduce || value === 0) {
      setDisplay(value);
      return;
    }

    const run = () => {
      if (started.current) return;
      started.current = true;
      const start = performance.now();
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        // easeOutExpo — fast then settles
        const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
        setDisplay(Math.round(eased * value));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };

    if (!onView) {
      run();
      return;
    }

    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          run();
          io.disconnect();
        }
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [value, duration, onView]);

  return (
    <span ref={ref} className={className} aria-label={String(value)}>
      {format ? display.toLocaleString() : display}
    </span>
  );
}
