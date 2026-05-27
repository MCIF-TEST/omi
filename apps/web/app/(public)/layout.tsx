/**
 * Public route group — no app shell, no nav, no auth gate.
 * Used for shareable reports at /r/[token].
 *
 * Print stylesheet lives inline below so the page is self-contained
 * when downloaded as a single HTML file.
 */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <style>{`
        @media print {
          .no-print { display: none !important; }
          body { background: #ffffff !important; color: #0b101d !important; }
          .report-page { background: #ffffff !important; color: #0b101d !important; box-shadow: none !important; }
          .report-card { border: 1px solid #d4d4d8 !important; background: #fafafa !important; page-break-inside: avoid; }
          .report-card * { color: #0b101d !important; }
          .report-muted { color: #6b7280 !important; }
          .report-accent { color: #0e7490 !important; }
          .report-tier-pill { border: 1px solid currentColor !important; background: transparent !important; }
          a { color: #0e7490 !important; text-decoration: none !important; }
          @page { margin: 18mm 16mm; }
        }
      `}</style>
      {children}
    </>
  );
}
