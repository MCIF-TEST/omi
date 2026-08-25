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
 * Scroll-triggered reveal. Element fades + eases in the first time it enters the
 * viewport, then stays put. Honors prefers-reduced-motion by rendering visible
 * immediately.
 *
 * IT FAILS OPEN, and that is the load-bearing part. The hidden state is
 * `opacity-0`, so anything that stops the observer from ever firing leaves the
 * content permanently invisible with nothing on the page to say so: no error, no
 * empty state, just a gap. On this site the one thing wrapped in a Reveal is the
 * free scan form on the front page, which is the whole pre-login conversion
 * path, so the failure would cost every anonymous visitor and be invisible in
 * every log.
 *
 * Same lesson as `AuthFormGate`'s 12-second timeout and the analyst's
 * "check back in a moment": a state with no terminal branch is not a loading
 * state, it is a silent failure. Two guards, both cheap:
 *
 *  - No `IntersectionObserver` (older browsers, some in-app webviews), or a
 *    constructor that throws: show the content at once.
 *  - A backstop timer. If the observer has not fired by then, show it anyway.
 *    Content below the fold is off-screen when this fires, so the only thing
 *    lost is an animation nobody was in a position to watch.
 */
const REVEAL_BACKSTOP_MS = 4000;

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
    const el = ref.current;
    if (reduce || !el || typeof IntersectionObserver === 'undefined') {
      setShown(true);
      return;
    }
    let io: IntersectionObserver | undefined;
    try {
      io = new IntersectionObserver(
        (entries) => {
          if (entries[0]?.isIntersecting) {
            setShown(true);
            io?.disconnect();
          }
        },
        { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
      );
      io.observe(el);
    } catch {
      setShown(true);
      return;
    }
    const backstop = setTimeout(() => setShown(true), REVEAL_BACKSTOP_MS);
    return () => {
      clearTimeout(backstop);
      io?.disconnect();
    };
  }, []);

  return (
    <Tag
      // @ts-expect-error. Ref typing across the polymorphic Tag union
      ref={ref}
      style={{ transitionDelay: shown ? `${delay}ms` : '0ms' }}
      className={cn(
        'transition-all duration-700 ease-omi will-change-transform',
        shown
          ? 'opacity-100 translate-x-0 translate-y-0 scale-100'
          // `reveal-pending` is what the <noscript> rule in the root layout overrides. With
          // scripting off nothing ever sets `shown`, so this element would stay at opacity 0
          // permanently: the markup is in the document, which is why a text extractor never
          // noticed, and invisible to anything that actually renders the page, including an
          // agent driving a headless browser with JavaScript disabled. On this site that is
          // the free scan form, so the cost is the entire pre-login conversion path.
          : cn('reveal-pending opacity-0', OFFSCREEN[from]),
        className,
      )}
    >
      {children}
    </Tag>
  );
}
