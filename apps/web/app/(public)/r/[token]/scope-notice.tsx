import Link from 'next/link';
import { Info } from 'lucide-react';

/**
 * What this report is claiming, stated before anyone reads a number.
 *
 * The page scores named, identifiable accounts whose owners never agreed to be analysed, and it gets
 * shared publicly. Someone arriving here, including the person it is about, should not have to infer
 * from tone whether we are calling them a bot. So it is said plainly, above the verdict.
 *
 * Deliberately NOT `no-print`. Every other interactive block on this page is hidden from the export,
 * but this one has to survive: the printed PDF is the version that gets circulated as evidence, and a
 * document making scored claims about people without its own scope statement attached is exactly the
 * artifact this notice exists to prevent.
 */
export function ScopeNotice() {
  return (
    <aside className="report-card rounded-md border border-border-1 bg-bg-elev/60 p-4 flex items-start gap-3">
      <Info size={15} className="text-fg-mute report-muted mt-0.5 shrink-0" aria-hidden />
      <p className="text-xs text-fg-dim leading-relaxed">
        <span className="text-fg font-medium">
          These scores are probabilistic readings of public behaviour, not findings of fact.
        </span>{' '}
        They describe how closely an account&apos;s public activity resembles patterns associated with
        bought or automated engagement. They are not an allegation that any person has broken a law or
        a platform rule, and they make no claim about who operates an account, whether money changed
        hands, or anyone&apos;s intent. Automated analysis is wrong sometimes, in both directions:
        businesses, fan accounts, news feeds, new users, and people writing in a second language can
        all resemble the patterns. Published for transparency about engagement, and meant to be
        checked rather than taken on trust.{' '}
        <Link href="/accuracy" className="text-accent hover:underline">
          Accuracy and scope
        </Link>
        .
      </p>
    </aside>
  );
}
