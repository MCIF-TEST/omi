'use client';

import { Printer } from 'lucide-react';

export function PrintButton() {
  return (
    <button
      onClick={() => window.print()}
      className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-accent-dim bg-accent/10 text-accent rounded-sm hover:bg-accent/20"
      aria-label="Print or save as PDF"
    >
      <Printer size={11} /> Print / PDF
    </button>
  );
}
