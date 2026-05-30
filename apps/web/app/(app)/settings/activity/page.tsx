import Link from 'next/link';
import { ArrowLeft, CheckCircle, RefreshCw, XCircle } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { apiServer } from '@/lib/api-server';
import { type ActivityLogResponse } from '@/lib/api';
import { timeAgo } from '@/lib/format';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Activity log — OMISPHERE' };

const SCAN_TYPE_LABELS: Record<string, string> = {
  comprehensive: 'Comprehensive',
  account: 'Account',
  video: 'Video',
  link: 'Link',
  bulk: 'Bulk',
};

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: { offset?: string };
}) {
  const offset = parseInt(searchParams.offset ?? '0', 10) || 0;
  const limit = 50;

  let log: ActivityLogResponse;
  try {
    log = await apiServer<ActivityLogResponse>(
      `/v1/activity?limit=${limit}&offset=${offset}`
    );
  } catch {
    log = { entries: [], total: 0, limit, offset, credits_spent_total: 0, credits_refunded_total: 0 };
  }

  const totalPages = Math.ceil(log.total / limit);
  const currentPage = Math.floor(offset / limit) + 1;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-fg-mute hover:text-fg-dim font-mono tracking-wider uppercase"
        >
          <ArrowLeft size={14} /> Settings
        </Link>
      </div>

      <header>
        <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase mb-1">Settings</p>
        <h1 className="text-2xl font-semibold text-fg tracking-tight">Activity log</h1>
        <p className="mt-1 text-sm text-fg-dim">Every scan you&apos;ve initiated, with credit usage.</p>
      </header>

      {/* Summary strip */}
      <div className="grid grid-cols-3 gap-3">
        <SumCard label="Total scans" value={log.total} />
        <SumCard label="Credits spent" value={log.credits_spent_total} accent />
        <SumCard label="Credits refunded" value={log.credits_refunded_total} />
      </div>

      <Card>
        <CardLabel>Scan history</CardLabel>
        {log.entries.length === 0 ? (
          <p className="text-sm text-fg-dim py-4">No scans yet.</p>
        ) : (
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-1">
                  {['Time', 'Target', 'Type', 'Credits', 'Status'].map((h) => (
                    <th
                      key={h}
                      className="px-3 py-2 text-left font-mono text-2xs tracking-wider uppercase text-fg-mute"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-1">
                {log.entries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-bg-elev-2/40 transition-colors">
                    <td className="px-3 py-2.5 font-mono text-xs text-fg-mute whitespace-nowrap">
                      {timeAgo(entry.created_at)}
                    </td>
                    <td className="px-3 py-2.5 text-fg max-w-[280px] truncate" title={entry.target_input ?? ''}>
                      {entry.target_input ? (
                        <span className="font-mono text-xs">{entry.target_input}</span>
                      ) : (
                        <span className="text-fg-faint">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <Badge variant="neutral">
                        {SCAN_TYPE_LABELS[entry.scan_type] ?? entry.scan_type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-fg-dim whitespace-nowrap">
                      {entry.credits_cost}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      {entry.refunded ? (
                        <span className="inline-flex items-center gap-1 text-xs text-amber-400 font-mono">
                          <RefreshCw size={10} /> Refunded
                        </span>
                      ) : entry.success ? (
                        <span className="inline-flex items-center gap-1 text-xs text-tier-low font-mono">
                          <CheckCircle size={10} /> OK
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-danger font-mono">
                          <XCircle size={10} /> Failed
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="flex items-center justify-between gap-4 font-mono text-xs text-fg-mute">
          <span>Page {currentPage} of {totalPages}</span>
          <div className="flex gap-2">
            {offset > 0 && (
              <Link
                href={`/settings/activity?offset=${Math.max(0, offset - limit)}`}
                className="px-3 py-1.5 border border-border-2 rounded-sm hover:border-border-hot transition-colors"
              >
                ← Previous
              </Link>
            )}
            {offset + limit < log.total && (
              <Link
                href={`/settings/activity?offset=${offset + limit}`}
                className="px-3 py-1.5 border border-border-2 rounded-sm hover:border-border-hot transition-colors"
              >
                Next →
              </Link>
            )}
          </div>
        </nav>
      )}
    </div>
  );
}

function SumCard({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-4">
      <div className="font-mono text-2xs tracking-wider uppercase text-fg-mute mb-1">{label}</div>
      <div className={`text-2xl font-semibold mono tracking-tight ${accent ? 'text-accent' : 'text-fg'}`}>
        {value.toLocaleString()}
      </div>
    </div>
  );
}
