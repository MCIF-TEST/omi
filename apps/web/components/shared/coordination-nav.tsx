import Link from 'next/link';
import { cn } from '@/lib/cn';

/**
 * The three coordination surfaces, and which is which.
 *
 * THEY ANSWER ONE QUESTION IN THREE VOCABULARIES and nothing on any of them said so. `/netdetect`
 * calls its output "network findings", `/narratives` calls its output "coordinated campaigns", and
 * `/graph` draws accounts you saved by hand. An operator moving between them has no way to tell
 * whether they are looking at three views of one thing or three different things, and the answer
 * is genuinely not obvious: they are two different detectors plus a workspace.
 *
 * THE DIFFERENCE THAT MATTERS IS WHICH ONE RUNS BY ITSELF. The cohort detector runs automatically
 * when a scan is saved and only ever sees accounts the per-account engine already scored at 70 or
 * above. The network detector never reads a score at all, which is why it can see an operation of
 * aged accounts that each look ordinary, and it is manual. So "nothing on /narratives" and "nothing
 * on /netdetect" are different statements, and neither is a clean bill of health.
 */

const SURFACES = [
  {
    href: '/netdetect',
    label: 'Formations',
    what: 'Score-blind, set-level, manual. Catches groups whose members each look ordinary.',
  },
  {
    href: '/narratives',
    label: 'Campaigns',
    what: 'Runs on every scan, over accounts already scored 70 or above.',
  },
  {
    href: '/graph',
    label: 'Graph',
    what: 'Accounts you saved, and what the accumulated evidence links them to.',
  },
] as const;

export function CoordinationNav({ current }: { current: '/netdetect' | '/narratives' | '/graph' }) {
  return (
    <nav aria-label="Coordination surfaces" className="flex flex-wrap gap-1.5">
      {SURFACES.map((s) => {
        const active = s.href === current;
        return (
          <Link
            key={s.href}
            href={s.href}
            title={s.what}
            aria-current={active ? 'page' : undefined}
            className={cn(
              'h-8 px-3 inline-flex items-center rounded-md border focus-hard',
              'font-mono text-2xs uppercase tracking-wider ease-omi',
              'transition-[color,background-color,border-color] duration-150',
              // REAL CLASSES ONLY. An opacity modifier on a palette token generates nothing in
              // this stylesheet (`bg-accent/10` and `border-accent/40` are both absent from the
              // built CSS), so a chip styled that way renders with no ground and no border while
              // typecheck, lint and every test stay green. That defect is already shipped in ~200
              // places here and is the owner's to fix as a palette change; the rule for new code
              // is not to add to it.
              active
                ? 'border-accent bg-bg-elev-2 text-accent'
                : 'border-border-1 text-fg-mute hover:text-fg',
            )}
          >
            {s.label}
          </Link>
        );
      })}
    </nav>
  );
}

/**
 * Why there are two detectors, stated once and shared.
 *
 * Kept beside the nav rather than written into each page, because three copies of an explanation
 * is how three copies drift, and this one is about the exact distinction an operator gets wrong.
 */
export function WhyTwoDetectors({ className }: { className?: string }) {
  return (
    <p className={cn('text-2xs text-fg-mute', className)}>
      Two detectors run here and they are not redundant. The campaign pass runs automatically on
      every scan but only sees accounts already scored 70 or above, so a disciplined operation using
      aged accounts is invisible to it by construction. The network detector never reads a score,
      which is what lets it see that operation, and it is manual because it names people on
      statistical evidence alone. An empty result from either is &quot;no mechanical tell was
      found&quot;, never &quot;these accounts are unrelated&quot;.
    </p>
  );
}
