'use client';

import { useEffect, useState } from 'react';
import { ChevronDown, Loader2, Play } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/cn';
import {
  listInvestigations,
  runNetdetect,
  type InvestigationSummary,
  type NetdetectRun,
} from '@/lib/api';
import { runVerdict, type RunOutcome } from '@/lib/netdetect-read';

/**
 * Start a detection from the page.
 *
 * THE QUEUE COULD NOT FILL ITSELF. Everything downstream of this panel, the finding queue, the
 * judgements, the calibration report that refuses to recommend anything below thirty of them, was
 * reachable only by findings that already existed, and the only way to create one was to send
 * `POST /v1/admin/netdetect/<slug>` by hand. The empty state literally printed that endpoint. So
 * the ground-truth path this whole page exists to feed was gated behind curl, one step further up
 * than the problem the page was built to solve.
 *
 * IT IS SAFE TO PUT BEHIND A BUTTON, which is why it is a button. The run costs nothing: no
 * provider call, no model call, no credit. It reads a payload that is already stored. The route's
 * own docstring says as much.
 *
 * THE OUTCOME IS NEVER RENDERED AS A BARE COUNT. Three of the four outcomes present as an empty
 * findings list and they are not the same statement about the accounts in that section, so the
 * result goes through `runVerdict` rather than through `findings.length`.
 */

// A HAIRLINE IN THE SEMANTIC COLOUR, NOT A TINTED FILL, for two reasons. The design language
// forbids gradient and glow fills and treats the hairline as the carrier of meaning; and an opacity
// modifier on a palette token (`bg-tier-elevated/5`) generates NOTHING in this stylesheet, so the
// tinted version would have rendered as a plain box while every check stayed green.
const OUTCOME_TONE: Record<RunOutcome, string> = {
  found: 'border-tier-elevated bg-bg-elev-2',
  refused: 'border-border-1 bg-bg-elev-2',
  unresolvable: 'border-tier-moderate bg-bg-elev-2',
  clean: 'border-border-1 bg-bg-elev-2',
};

const OUTCOME_LED: Record<RunOutcome, string> = {
  found: 'led led-warn',
  refused: 'led led-off',
  unresolvable: 'led led-work',
  clean: 'led led-ok',
};

export function RunPanel({ onRecorded }: { onRecorded?: () => void }) {
  const [investigations, setInvestigations] = useState<InvestigationSummary[] | null>(null);
  const [slug, setSlug] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<NetdetectRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState(false);
  const [record, setRecord] = useState(true);
  const [shuffles, setShuffles] = useState(24);

  useEffect(() => {
    let live = true;
    listInvestigations(50)
      .then((r) => {
        if (!live) return;
        setInvestigations(r.investigations);
        // Preselect the newest, so the common case is one click. The picker still shows what was
        // chosen: a Run button that silently acts on something the operator did not pick is worse
        // than one that needs a selection.
        if (r.investigations.length > 0) setSlug(r.investigations[0].slug);
      })
      .catch(() => live && setInvestigations([]));
    return () => {
      live = false;
    };
  }, []);

  const run = async () => {
    if (!slug) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await runNetdetect(slug, { shuffles, record });
      setResult(r);
      // Only tell the queue to reload when something could actually have been written to it.
      if (record && r.findings.length > 0) onRecorded?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The run could not be started.');
    } finally {
      setBusy(false);
    }
  };

  const verdict = result ? runVerdict(result) : null;
  const chosen = investigations?.find((i) => i.slug === slug) ?? null;

  return (
    <Card flush ticks>
      <div className="panel-head">
        <span className="meta meta-hi">1 · Run</span>
        <span className="meta">costs nothing</span>
      </div>
      <div className="panel-body space-y-3">
        <p className="text-xs text-fg-dim">
          Reads one investigation you have already scanned and looks for sets of accounts sharing
          improbably many rare behaviours. No model call and no credit: it re-reads stored evidence,
          so it is safe to run as often as you like.
        </p>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1 min-w-0">
            <label className="meta mb-1 block" htmlFor="netdetect-slug">
              Investigation
            </label>
            {investigations === null ? (
              <p className="flex items-center gap-2 text-xs text-fg-dim h-9">
                <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
                Loading your scans
              </p>
            ) : investigations.length === 0 ? (
              <p className="text-xs text-fg-dim h-9 flex items-center">
                No scans yet. Run one from Investigate and it appears here.
              </p>
            ) : (
              <select
                id="netdetect-slug"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className={cn(
                  'w-full h-9 rounded-md border border-border-1 bg-bg px-2 text-sm focus-hard',
                )}
              >
                {investigations.map((i) => (
                  <option key={i.slug} value={i.slug}>
                    {i.label || i.slug}
                  </option>
                ))}
              </select>
            )}
          </div>
          <Button onClick={run} disabled={busy || !slug}>
            {busy ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Play className="h-3.5 w-3.5" aria-hidden />
            )}
            {busy ? 'Detecting' : 'Run detector'}
          </Button>
        </div>

        {chosen ? (
          <p className="font-mono text-2xs text-fg-mute break-all">
            {chosen.input_url}
          </p>
        ) : null}

        <button
          type="button"
          onClick={() => setAdvanced((v) => !v)}
          className="flex items-center gap-1 meta text-fg-mute hover:text-fg focus-hard"
        >
          <ChevronDown
            className={cn('h-3 w-3 transition-transform duration-150 ease-omi', advanced && 'rotate-180')}
            aria-hidden
          />
          Options
        </button>

        {advanced ? (
          <div className="space-y-3 rounded-md border border-border-1 p-3">
            <div>
              <label className="meta mb-1 block" htmlFor="netdetect-shuffles">
                Null shuffles
              </label>
              <input
                id="netdetect-shuffles"
                type="number"
                min={1}
                max={200}
                value={shuffles}
                onChange={(e) => setShuffles(Number(e.target.value) || 1)}
                className="h-9 w-28 rounded-md border border-border-1 bg-bg px-2 text-sm focus-hard"
              />
              {/* The coupling, stated where somebody would change the number. At quantile q the
                  smallest p-value expressible is 1/(K+1), so a low K cannot report anything at all
                  however strong the evidence, and the run comes back looking like a clean section. */}
              <p className="mt-1 text-2xs text-fg-mute">
                How many degree-preserving shuffles the search correction is built from. Below about
                19 the detector cannot express a small enough p-value to report anything, whatever
                the data holds. Higher is slower and stricter.
              </p>
            </div>
            <label className="flex items-start gap-2 text-xs text-fg-dim">
              <input
                type="checkbox"
                checked={record}
                onChange={(e) => setRecord(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                Record the findings.
                <span className="block text-2xs text-fg-mute">
                  Off gives you the answer and stores nothing, which is what you want while tuning:
                  a stored row per button press turns the queue into a log. Recording also folds the
                  pairs into the accumulating graph that future findings are corroborated against.
                </span>
              </span>
            </label>
          </div>
        ) : null}

        {error ? <p className="text-xs text-tier-high">{error}</p> : null}

        {result && verdict ? (
          <div className={cn('rounded-md border p-3 space-y-2', OUTCOME_TONE[verdict.outcome])}>
            <div className="flex items-center gap-2">
              <span className={OUTCOME_LED[verdict.outcome]} aria-hidden />
              <span className="meta meta-hi">{verdict.title}</span>
            </div>
            <p className="text-xs text-fg-dim">{verdict.detail}</p>
            <div className="flex flex-wrap gap-4 pt-1">
              <Readout label="Corpus" value={String(result.corpus_size)} />
              <Readout label="Rare features" value={String(result.rare_features)} />
              <Readout label="Shuffles" value={String(result.null_shuffles)} />
              <Readout
                label="Threshold"
                value={result.null_threshold === null ? '-' : result.null_threshold.toFixed(2)}
              />
            </div>
            {result.findings.length > 0 && !record ? (
              <p className="text-2xs text-fg-mute">
                Not recorded, so nothing reached the queue below. Re-run with recording on to judge
                these.
              </p>
            ) : null}
            {result.findings.length > 0 && record ? (
              <p className="text-2xs text-fg-mute">
                {result.recorded ?? result.findings.length} stored in the queue below
                {result.accumulated ? `, ${result.accumulated} pairs folded into the graph` : ''}.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="readout-v">
      <span className="meta">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  );
}
