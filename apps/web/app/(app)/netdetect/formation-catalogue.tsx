'use client';

import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/cn';
import { listFormations, type Formation } from '@/lib/api';

/**
 * The operations this deployment knows about.
 *
 * The sweep can place an account in a formation, and until now nothing could show you the
 * formations themselves. A catalogue you cannot read is a catalogue nobody curates, and these rows
 * are what every future sweep is measured against.
 *
 * PHASE IS THE COLUMN TO READ. `dormant` is the only state in this package derived from an event
 * NOT happening, so it exists only because the monitoring pass ages the catalogue; `resurgent` is
 * the one a per-run detector can never report at all, because it needs the entity to have survived
 * the quiet period.
 */
const PHASE_TONE: Record<string, string> = {
  forming: 'text-tier-moderate',
  active: 'text-tier-high',
  resurgent: 'text-tier-elevated',
  dormant: 'text-fg-mute',
};

export function FormationCatalogue() {
  const [rows, setRows] = useState<Formation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    listFormations()
      .then((r) => live && setRows(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not load formations.'));
    return () => {
      live = false;
    };
  }, []);

  return (
    <Card flush>
      <div className="panel-head">
        <span className="meta meta-hi">Known operations</span>
        <span className="meta">{rows ? `${rows.length}` : ''}</span>
      </div>
      <div className="panel-body">
        {error ? <p className="text-xs text-tier-high">{error}</p> : null}

        {!rows && !error ? (
          <p className="flex items-center gap-2 text-xs text-fg-dim">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading the catalogue
          </p>
        ) : null}

        {rows && rows.length === 0 ? (
          <p className="text-xs text-fg-dim">
            No operation has been catalogued yet. One is recorded the first time the detector finds
            a formation, so this fills as investigations are run.
          </p>
        ) : null}

        {rows && rows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="rack-table">
              <thead>
                <tr>
                  <th className="meta text-left">Operation</th>
                  <th className="meta text-left">Phase</th>
                  <th className="meta text-right">Members</th>
                  <th className="meta text-right">Posts</th>
                  <th className="meta text-left">Posture</th>
                  <th className="meta text-left">Last seen</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((f) => (
                  <tr key={f.formation_key}>
                    <td className="font-mono text-xs">{f.label || f.formation_key}</td>
                    <td className={cn('meta', PHASE_TONE[f.phase] ?? 'text-fg-dim')}>{f.phase}</td>
                    <td className="text-right font-mono text-xs tabular-nums">{f.member_count}</td>
                    {/* Distinct posts, not runs: re-scanning one post cannot inflate this. */}
                    <td className="text-right font-mono text-xs tabular-nums">{f.context_count}</td>
                    <td
                      className={cn(
                        'meta',
                        f.composition?.posture === 'concealed'
                          ? 'text-tier-high'
                          : 'text-fg-dim',
                      )}
                    >
                      {f.composition?.posture ?? 'unknown'}
                    </td>
                    <td className="font-mono text-2xs text-fg-mute">
                      {f.last_seen ? f.last_seen.slice(0, 10) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {/* The inverted reading, stated where the column is rather than left to be inferred. */}
        {rows && rows.some((f) => f.composition?.posture === 'concealed') ? (
          <p className="mt-3 text-2xs text-fg-mute">
            A concealed operation is the more dangerous finding: its members read as ordinary
            accounts individually, so the per-account engine would not have flagged any of them and
            the coordination is the whole of the evidence.
          </p>
        ) : null}
      </div>
    </Card>
  );
}
