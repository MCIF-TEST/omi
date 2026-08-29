'use client';

import { useState } from 'react';
import { Loader2, Radar } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { sweepFormations, type FormationSweep } from '@/lib/api';

/**
 * Weigh a whole comment section against every catalogued operation.
 *
 * The single-account route answers "does THIS account belong to THAT operation", which needs an
 * operator to suspect both already. When a comment section lands nobody suspects anything, so this
 * asks the useful direction: is anybody here part of something we have already recorded?
 *
 * THE THREE OUTCOMES ARE RENDERED SEPARATELY AND THAT IS THE POINT. "Nothing catalogued yet",
 * "weighed and matched nothing", and "placed" are different statements about named people, and two
 * of them present as an empty list. Same distinction the API draws with `nothing_catalogued`, and
 * the same one `attachment_checked` draws on a finding.
 */
export function FormationSweep() {
  const [slug, setSlug] = useState('');
  const [result, setResult] = useState<FormationSweep | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    const target = slug.trim();
    if (!target) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await sweepFormations(target));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The sweep could not be run.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card flush ticks>
      <div className="panel-head">
        <span className="meta meta-hi">Sweep a section</span>
        <span className="meta">Formations</span>
      </div>
      <div className="panel-body space-y-4">
        <p className="text-xs text-fg-dim">
          Weigh every account an investigation scanned against every operation this deployment has
          catalogued. Costs nothing: no model call, no credit, and nothing is written.
        </p>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void run();
            }}
            placeholder="Investigation slug"
            aria-label="Investigation slug"
            className="flex-1 min-w-0"
          />
          <Button onClick={() => void run()} disabled={busy || !slug.trim()} className="shrink-0">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Radar className="h-3.5 w-3.5" />}
            <span className="ml-1.5">Sweep</span>
          </Button>
        </div>

        {error ? <p className="text-xs text-tier-high">{error}</p> : null}

        {result ? (
          <div className="space-y-3">
            {/* THREE OUTCOMES, never inferred from an empty list. */}
            {result.nothing_catalogued ? (
              <p className="text-xs text-fg-dim">
                No operation has been catalogued yet, so nothing was weighed. That is not the same
                as these accounts matching nothing.
              </p>
            ) : (
              <>
                <div className="flex flex-wrap gap-x-6 gap-y-1">
                  <span className="readout">
                    <span className="meta">Weighed</span>
                    <span className="stat-value">{result.accounts_weighed}</span>
                  </span>
                  <span className="readout">
                    <span className="meta">Formations</span>
                    <span className="stat-value">{result.formations_considered}</span>
                  </span>
                  <span className="readout">
                    <span className="meta">Placed</span>
                    <span className="stat-value">{result.placed.length}</span>
                  </span>
                  <span className="readout">
                    <span className="meta">No match</span>
                    <span className="stat-value">{result.unplaced}</span>
                  </span>
                  {/* THE FIGURE TO READ FIRST. An account the per-account engine already flags is
                      one an analyst could have found without this; an account that would pass an
                      individual review and still matches a known operation is the finding nothing
                      else in the product can produce. */}
                  {result.concealed > 0 ? (
                    <span className="readout">
                      <span className="meta meta-on">Would pass review</span>
                      <span className="stat-value text-tier-high">{result.concealed}</span>
                    </span>
                  ) : null}
                </div>

                {result.truncated ? (
                  <p className="text-xs text-tier-elevated">
                    The account cap was reached, so this answers about a subset and says nothing
                    about the rest.
                  </p>
                ) : null}

                {result.placed.length > 0 ? (
                  <ul className="space-y-2">
                    {result.placed.map((p) => (
                      <li key={p.external_id} className="rule-rack border-l-2 border-tier-high pl-2.5">
                        <div className="flex flex-wrap items-baseline gap-x-2">
                          <span className="font-mono text-xs text-fg">{p.handle}</span>
                          <span className="meta">
                            {p.assignment.label || p.assignment.formation_key}
                          </span>
                          {p.assignment.phase ? (
                            <span className="meta text-fg-mute">{p.assignment.phase}</span>
                          ) : null}
                        </div>
                        <p className="mt-0.5 text-2xs text-fg-mute">
                          {Math.round(p.assignment.posterior * 100)}%
                          {p.omi_score !== null ? ` · OMI ${Math.round(p.omi_score)}` : ''}
                          {p.concealed ? ' · would pass an individual review' : ''} ·{' '}
                          {p.assignment.matched
                            .slice(0, 2)
                            .map((m) => m.sentence)
                            .join(' · ')}
                        </p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-xs text-fg-dim">
                    No scanned account matched a catalogued operation.
                  </p>
                )}
              </>
            )}

            {/* Shipped with the numbers rather than left in a docstring, for the same reason the
                run response carries its membership note: an empty result is the one most likely to
                be read as a verdict it is not. */}
            <p className="text-2xs text-fg-mute">{result.not_a_clearance}</p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
