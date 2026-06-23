import { ShieldCheck, AlertTriangle, Check, Minus } from 'lucide-react';

/**
 * TrustList — one column of an evidence-for / evidence-weakening split. The
 * platform's discipline is that no verdict is shown without BOTH what supports
 * it and what weakens it; this is the presentational half of that contract.
 * Each item carries an icon (check = a signal that fired / supports; dash = a
 * caveat / silent signal), and the column is faintly tinted to its meaning so
 * the two read as distinct at a glance — never colour alone. Empty states are
 * explicit so absence of counter-evidence is itself visible.
 */
export function TrustList({
  tone,
  title,
  items,
  empty,
}: {
  tone: 'for' | 'weakening';
  title: string;
  items: readonly string[];
  empty: string;
}) {
  const isFor = tone === 'for';
  const Head = isFor ? ShieldCheck : AlertTriangle;
  const ItemIcon = isFor ? Check : Minus;
  const headCls = isFor ? 'text-tier-low' : 'text-tier-moderate';
  const wrapCls = isFor
    ? 'border-tier-low/25 bg-tier-low/[0.04]'
    : 'border-tier-moderate/25 bg-tier-moderate/[0.04]';
  const iconCls = isFor ? 'text-tier-low' : 'text-fg-mute';
  return (
    <div className={`rounded-xl border p-4 ${wrapCls}`}>
      <div className={`flex items-center gap-2 text-xs font-semibold uppercase tracking-wide ${headCls} mb-3`}>
        <Head size={13} strokeWidth={2.2} />
        {title}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-fg-mute italic">{empty}</p>
      ) : (
        <ul className="space-y-2.5">
          {items.map((it, i) => (
            <li key={i} className="flex items-start gap-2.5 text-sm text-fg-dim leading-snug">
              <ItemIcon size={14} strokeWidth={2.5} className={`shrink-0 mt-0.5 ${iconCls}`} />
              <span>{it}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The two columns side by side — evidence-for and evidence-weakening. */
export function EvidenceForAgainst({
  forItems,
  againstItems,
  forEmpty = 'No specific supporting reasons recorded.',
  againstEmpty = 'No data-quality caveats — confidence is well-supported.',
}: {
  forItems: readonly string[];
  againstItems: readonly string[];
  forEmpty?: string;
  againstEmpty?: string;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      <TrustList tone="for" title="Evidence for" items={forItems} empty={forEmpty} />
      <TrustList tone="weakening" title="Evidence weakening" items={againstItems} empty={againstEmpty} />
    </div>
  );
}
