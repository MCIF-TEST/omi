/**
 * Masthead for the standalone public pages (pricing, accuracy, about, terms, privacy).
 *
 * The front page's chapters carry an index numeral, a hard rule and a left axis. These pages are
 * single documents rather than chaptered arguments, so they take the same parts at smaller scale:
 * an index label, the display face, a left edge everything else lines up to.
 *
 * Left-anchored on purpose. Every one of these pages used to centre its header, which is the
 * single fastest way to make a page read as marketing rather than as a document.
 */
export function PageMasthead({
  index,
  eyebrow,
  title,
  lede,
}: {
  index: string;
  eyebrow: string;
  title: string;
  lede?: string;
}) {
  return (
    <header className="mb-10 md:mb-12">
      <div className="flex items-center gap-3 mb-6">
        <span className="idx">{index}</span>
        <span className="h-px w-8 bg-border-hot" aria-hidden />
        <span className="meta meta-hi">{eyebrow}</span>
      </div>

      <h1
        className="display-hard text-fg"
        style={{ fontSize: 'clamp(2rem, 5.2vw, 3.25rem)' }}
      >
        {title}
      </h1>

      {lede && (
        <p className="text-[0.9375rem] text-fg-dim leading-relaxed mt-5 max-w-[58ch]">{lede}</p>
      )}

      <hr className="rule-chapter mt-8" />
    </header>
  );
}

/**
 * A titled block inside one of those pages. Hairline rule above, mono label, then content: the
 * same separator logic the front page uses between chapters, at document scale.
 */
export function PageSection({
  label,
  children,
  className = '',
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`mt-10 md:mt-12 ${className}`}>
      <h2 className="meta meta-hi mb-4">{label}</h2>
      {children}
    </section>
  );
}
