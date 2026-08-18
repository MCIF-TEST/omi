'use client';

import { useEffect, useState } from 'react';

/**
 * Thin gradient progress bar pinned to the top of the viewport that
 * fills as the page scrolls. Pure decoration, a small signal of
 * "this site is alive." Hidden from assistive tech.
 */
export function ScrollProgress() {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    let raf = 0;
    const onScroll = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const h = document.documentElement;
        const max = h.scrollHeight - h.clientHeight;
        setPct(max > 0 ? (h.scrollTop / max) * 100 : 0);
      });
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
    };
  }, []);

  return (
    <div className="fixed top-0 left-0 right-0 z-50 h-0.5 pointer-events-none" aria-hidden>
      <div
        // Flat identity blue. This was `bg-brand-gradient`, which is the
        // suspicion ramp (authentic to highly-suspicious). The design language
        // reserves that ramp for surfaces where the scale IS the subject, so a
        // reader scrolling to the end of a report watched the bar run red: the
        // page's own scroll position rendered as a threat reading.
        className="h-full bg-accent transition-[width] duration-150 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
