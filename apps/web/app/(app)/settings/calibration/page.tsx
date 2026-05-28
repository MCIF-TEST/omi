import Link from 'next/link';
import { redirect } from 'next/navigation';
import { ArrowLeft, Database, Target, AlertTriangle } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { apiServer } from '@/lib/api-server';
import { getCurrentUser } from '@/lib/auth';
import {
  type AccountLabelsResponse,
  type CalibrationEvaluation,
} from '@/lib/api';

export const metadata = { title: 'Calibration — OMISPHERE' };
export const dynamic = 'force-dynamic';

export default async function CalibrationPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) {
    redirect('/settings');
  }

  const [labels, evalAll, evalHigh] = await Promise.all([
    apiServer<AccountLabelsResponse>('/v1/labels?limit=1000').catch(() => ({
      total: 0, labels: [], by_label: {}, by_source: {},
    })),
    apiServer<CalibrationEvaluation>('/v1/labels/calibration/evaluate?min_confidence=medium').catch(() => ({
      n_cases: 0, message: 'Evaluator unavailable',
    })),
    apiServer<CalibrationEvaluation>('/v1/labels/calibration/evaluate?min_confidence=high').catch(() => ({
      n_cases: 0, message: 'Evaluator unavailable',
    })),
  ]);

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg-dim font-mono tracking-wider uppercase mb-4"
        >
          <ArrowLeft size={14} /> Back to settings
        </Link>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">
          Admin · ground truth
        </p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">Calibration</h1>
        <p className="mt-2 text-sm text-fg-dim max-w-2xl leading-relaxed">
          Live calibration metrics from the labels you and other admins have
          attached to accounts. Updates as soon as a label is saved — no
          extra YouTube quota consumed (the harness uses persisted scan
          results, not fresh API calls).
        </p>
      </div>

      {/* Corpus stats */}
      <Card>
        <CardLabel>Corpus</CardLabel>
        {labels.total === 0 ? (
          <>
            <CardTitle>No labeled accounts yet</CardTitle>
            <p className="text-sm text-fg-dim mb-4 max-w-xl leading-relaxed">
              Visit any account&apos;s profile page (an admin badge appears on the
              label widget there) and tag accounts you&apos;ve manually reviewed.
              Each label adds one case to this corpus.
            </p>
            <p className="font-mono text-2xs text-fg-mute uppercase tracking-wider">
              Tip: YouTube-suspension labels are auto-recorded when a rescan
              hits channelSuspended / channelClosed.
            </p>
          </>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3 mb-4">
              <Stat icon={<Database size={12} />} label="Total labels" value={labels.total} />
              <Stat icon={<Target size={12} />} label="By label kinds" value={Object.keys(labels.by_label).length} />
              <Stat
                icon={<AlertTriangle size={12} />}
                label="Auto-suspension"
                value={(labels.by_source as Record<string, number>).youtube_suspension ?? 0}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <BreakdownTable title="By kind" data={labels.by_label} />
              <BreakdownTable title="By source" data={labels.by_source} />
            </div>
          </>
        )}
      </Card>

      {/* Evaluation against persisted scans */}
      <EvalCard
        title="All labels (medium+ confidence)"
        evaluation={evalAll}
      />
      <EvalCard
        title="High-confidence only"
        evaluation={evalHigh}
      />

      {/* Method notes */}
      <Card>
        <CardLabel>Methodology</CardLabel>
        <p className="text-sm text-fg-dim leading-relaxed mb-3">
          For each labeled account we look at the most recent persisted{' '}
          <code className="font-mono text-accent">Scan</code> row — what the engine returned during
          its last evaluation. We compare:
        </p>
        <ul className="text-sm text-fg-dim space-y-2 mb-4 ml-4 list-disc">
          <li>
            <span className="text-fg">Tier accuracy</span> — exact match between predicted tier
            and labeled <span className="font-mono text-accent">expected_tier</span>.
          </li>
          <li>
            <span className="text-fg">Brier score</span> — mean squared error between the engine&apos;s
            probability and the midpoint of the labeled tier (lower is better).
          </li>
          <li>
            <span className="text-fg">Per-tier precision / recall / F1</span> — surfaces which
            tiers we systematically over- or under-predict.
          </li>
          <li>
            <span className="text-fg">Per-label accuracy</span> — &ldquo;we get bots right 80% of the
            time but only human-vs-spam right 40% of the time&rdquo; — the diagnostic.
          </li>
        </ul>
        <p className="text-sm text-fg-dim leading-relaxed">
          Run the offline harness against the same corpus with:
        </p>
        <pre className="mt-2 bg-bg-elev border border-border-1 rounded-sm px-3 py-2 font-mono text-xs text-fg-dim overflow-x-auto">
{`cd apps/api
python -m scripts.calibrate --from-db
python -m scripts.calibrate --from-db --min-confidence high`}
        </pre>
      </Card>
    </div>
  );
}

function Stat({
  icon, label, value,
}: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-sm p-3">
      <div className="flex items-center gap-1 font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1">
        {icon}{label}
      </div>
      <div className="font-mono text-xl font-semibold tabular-nums text-fg">{value}</div>
    </div>
  );
}

function BreakdownTable({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) {
    return (
      <div>
        <h3 className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">{title}</h3>
        <p className="text-xs text-fg-faint">No data yet.</p>
      </div>
    );
  }
  return (
    <div>
      <h3 className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">{title}</h3>
      <ul className="space-y-1.5 text-sm">
        {entries.map(([k, v]) => (
          <li key={k} className="flex items-center justify-between font-mono">
            <span className="text-fg-dim">{k.replace(/_/g, ' ')}</span>
            <span className="text-fg tabular-nums">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvalCard({
  title, evaluation: e,
}: { title: string; evaluation: CalibrationEvaluation }) {
  return (
    <Card>
      <CardLabel>Evaluation · {title}</CardLabel>
      {e.n_cases === 0 ? (
        <p className="text-sm text-fg-dim italic">{e.message || 'No data.'}</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-3 mb-5">
            <Metric label="Cases evaluated" value={e.n_cases} tone="neutral" />
            <Metric
              label="Tier accuracy"
              value={`${Math.round((e.tier_accuracy ?? 0) * 100)}%`}
              tone={(e.tier_accuracy ?? 0) >= 0.7 ? 'good' : (e.tier_accuracy ?? 0) >= 0.4 ? 'warn' : 'bad'}
            />
            <Metric
              label="Macro F1"
              value={(e.macro_f1 ?? 0).toFixed(2)}
              tone={(e.macro_f1 ?? 0) >= 0.6 ? 'good' : (e.macro_f1 ?? 0) >= 0.3 ? 'warn' : 'bad'}
            />
          </div>

          {e.per_tier && (
            <div className="mb-5">
              <h3 className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
                Per-tier precision / recall / F1
              </h3>
              <div className="overflow-x-auto -mx-2">
                <table className="w-full text-sm font-mono">
                  <thead>
                    <tr className="text-left text-2xs uppercase tracking-wider text-fg-mute border-b border-border-1">
                      <th className="px-2 py-1.5 font-normal">Tier</th>
                      <th className="px-2 py-1.5 font-normal text-right">Precision</th>
                      <th className="px-2 py-1.5 font-normal text-right">Recall</th>
                      <th className="px-2 py-1.5 font-normal text-right">F1</th>
                      <th className="px-2 py-1.5 font-normal text-right">Support</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(['low', 'moderate', 'elevated', 'high'] as const).map((t) => {
                      const m = e.per_tier?.[t];
                      if (!m || m.support === 0) {
                        return (
                          <tr key={t} className="border-b border-border-1/40">
                            <td className="px-2 py-1.5 text-fg-dim">{t}</td>
                            <td className="px-2 py-1.5 text-right text-fg-faint" colSpan={4}>
                              no cases
                            </td>
                          </tr>
                        );
                      }
                      return (
                        <tr key={t} className="border-b border-border-1/40">
                          <td className="px-2 py-1.5 text-fg-dim">{t}</td>
                          <td className="px-2 py-1.5 text-right text-fg tabular-nums">{m.precision.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right text-fg tabular-nums">{m.recall.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right text-fg tabular-nums">{m.f1.toFixed(2)}</td>
                          <td className="px-2 py-1.5 text-right text-fg-mute tabular-nums">{m.support}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {e.per_label_accuracy && Object.keys(e.per_label_accuracy).length > 0 && (
            <div>
              <h3 className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-2">
                Tier accuracy by label
              </h3>
              <ul className="space-y-1.5 text-sm">
                {Object.entries(e.per_label_accuracy).sort(([, a], [, b]) => b - a).map(([k, v]) => (
                  <li key={k} className="flex items-center justify-between font-mono">
                    <span className="text-fg-dim">{k.replace(/_/g, ' ')}</span>
                    <span className="text-fg tabular-nums">{Math.round(v * 100)}%</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function Metric({
  label, value, tone,
}: { label: string; value: string | number; tone: 'good' | 'warn' | 'bad' | 'neutral' }) {
  const color = {
    good: 'text-tier-low',
    warn: 'text-tier-moderate',
    bad: 'text-tier-high',
    neutral: 'text-fg',
  }[tone];
  return (
    <div className="bg-bg-elev border border-border-1 rounded-sm p-3">
      <div className="font-mono text-2xs text-fg-mute uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono text-2xl font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}
