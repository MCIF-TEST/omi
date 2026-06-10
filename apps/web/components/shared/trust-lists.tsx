import { ShieldCheck, AlertTriangle } from 'lucide-react';

/**
 * TrustList — one column of an evidence-for / evidence-weakening split. The
 * platform's discipline is that no verdict is shown without BOTH what supports
 * it and what weakens it; this is the presentational half of that contract.
 * Empty states are rendered explicitly so absence of counter-evidence is itself
 * visible (not silently omitted).
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
  const headCls = tone === 'for' ? 'text-accent' : 'text-tier-moderate';
  const Icon = tone === 'for' ? ShieldCheck : AlertTriangle;
  return (
    <div className="bg-bg/40 border border-border-1/70 rounded-md p-4">
      <div
        className={`flex items-center gap-1.5 font-mono text-2xs uppercase tracking-wider ${headCls} mb-2.5`}
      >
        <Icon size={12} />
        {title}
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-fg-mute italic">{empty}</p>
      ) : (
        <ul className="space-y-1.5 text-sm text-fg-dim">
          {items.map((it, i) => (
            <li key={i} className="leading-snug">
              <span className="text-fg-faint mr-1">·</span>
              {it}
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
      <TrustList
        tone="weakening"
        title="Evidence weakening / uncertainty"
        items={againstItems}
        empty={againstEmpty}
      />
    </div>
  );
}
