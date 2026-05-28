'use client';

import { useState } from 'react';
import { Printer, Check, Link2 } from 'lucide-react';

export function PrintButton() {
  return (
    <button
      onClick={() => window.print()}
      className="font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border border-accent-dim bg-accent/10 text-accent rounded-sm hover:bg-accent/20 transition-colors"
      aria-label="Save as PDF — uses browser's print-to-PDF"
      title="Save as PDF (Cmd/Ctrl+P)"
    >
      <Printer size={11} /> Save as PDF
    </button>
  );
}

export function CopyLinkButton({ url }: { url: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } catch {/* user can manually copy from address bar */}
      }}
      className={`font-mono text-2xs tracking-wider uppercase px-2.5 h-7 inline-flex items-center gap-1.5 border rounded-sm transition-colors ${
        copied
          ? 'border-tier-low/40 bg-tier-low/10 text-tier-low'
          : 'border-border-2 text-fg-dim hover:text-fg hover:border-border-hot'
      }`}
      aria-label="Copy share URL to clipboard"
    >
      {copied ? <Check size={11} /> : <Link2 size={11} />}
      {copied ? 'Copied' : 'Copy link'}
    </button>
  );
}
