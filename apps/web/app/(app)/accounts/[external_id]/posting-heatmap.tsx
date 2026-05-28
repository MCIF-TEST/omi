'use client';

import { Clock } from 'lucide-react';
import type { AuthorCommentRow } from '@/lib/api';

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

interface Props {
  comments: AuthorCommentRow[];
}

/**
 * Day-of-week × hour-of-day heatmap built from ingested comment timestamps.
 * Helps spot bot-like posting patterns (e.g. 24/7 uniform activity, or
 * a tight nightly window suggesting timezone tells).
 */
export function PostingHeatmap({ comments }: Props) {
  if (comments.length === 0) return null;

  // Build the bucket grid (day × hour)
  const grid: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));
  let max = 0;
  for (const row of comments) {
    const d = new Date(row.comment.observed_at);
    if (isNaN(d.getTime())) continue;
    const day = d.getDay();
    const hour = d.getHours();
    grid[day][hour]++;
    if (grid[day][hour] > max) max = grid[day][hour];
  }

  if (max === 0) return null;

  // Active range — find earliest and latest hours with any activity
  const activeHours = HOURS.filter((h) => grid.some((row) => row[h] > 0));
  const earliestHr = activeHours[0];
  const latestHr = activeHours[activeHours.length - 1];

  // Coverage % — what fraction of all 168 (day × hour) buckets have activity
  let nonEmpty = 0;
  for (const row of grid) for (const v of row) if (v > 0) nonEmpty++;
  const coverage = Math.round((nonEmpty / 168) * 100);

  // Pattern read
  let pattern = 'Concentrated';
  let patternColor = 'text-fg-dim';
  if (coverage >= 70) {
    pattern = 'Round-the-clock';
    patternColor = 'text-tier-high';
  } else if (coverage >= 40) {
    pattern = 'Broad';
    patternColor = 'text-tier-elevated';
  } else if (coverage <= 12) {
    pattern = 'Tight window';
    patternColor = 'text-tier-low';
  }

  return (
    <div className="bg-bg-elev border border-border-1 rounded-md p-5">
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="flex items-center gap-2">
          <Clock size={14} className="text-accent" />
          <p className="font-mono text-2xs tracking-[0.18em] text-fg-mute uppercase">
            Posting pattern — when they comment
          </p>
        </div>
        <div className="flex items-center gap-4 font-mono text-2xs">
          <span className="text-fg-mute uppercase tracking-wider">
            Pattern: <span className={`${patternColor} font-medium`}>{pattern}</span>
          </span>
          <span className="text-fg-mute uppercase tracking-wider">
            Coverage: <span className="text-fg tabular-nums">{coverage}%</span>
          </span>
        </div>
      </div>

      {/* Heatmap grid */}
      <div className="overflow-x-auto -mx-1 px-1">
        <div className="min-w-[560px]">
          {/* Hour labels along the top */}
          <div className="flex items-end gap-px ml-9 mb-1">
            {HOURS.map((h) => (
              <div
                key={h}
                className="flex-1 font-mono text-[9px] text-fg-faint tabular-nums text-center"
              >
                {h % 3 === 0 ? h : ''}
              </div>
            ))}
          </div>

          {/* Day rows */}
          {DAYS.map((day, di) => (
            <div key={day} className="flex items-center gap-px mb-px">
              <div className="w-9 font-mono text-2xs text-fg-mute uppercase tracking-wider text-right pr-2">
                {day}
              </div>
              {HOURS.map((h) => {
                const count = grid[di][h];
                const intensity = max > 0 ? count / max : 0;
                return (
                  <div
                    key={h}
                    className="flex-1 aspect-square rounded-[2px] transition-all"
                    style={{
                      backgroundColor:
                        intensity === 0
                          ? 'rgba(255,255,255,0.04)'
                          : `rgba(96, 165, 250, ${Math.max(0.15, intensity)})`,
                    }}
                    title={`${day} ${h}:00 — ${count} comment${count === 1 ? '' : 's'}`}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center justify-between gap-3 font-mono text-2xs text-fg-mute flex-wrap">
        <div className="flex items-center gap-2">
          <span className="uppercase tracking-wider">Activity range</span>
          <span className="tabular-nums text-fg-dim">
            {String(earliestHr).padStart(2, '0')}:00 – {String(latestHr).padStart(2, '0')}:59 UTC
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="uppercase tracking-wider">Less</span>
          {[0.15, 0.35, 0.55, 0.75, 0.95].map((a) => (
            <div
              key={a}
              className="w-3 h-3 rounded-[2px]"
              style={{ backgroundColor: `rgba(96, 165, 250, ${a})` }}
            />
          ))}
          <span className="uppercase tracking-wider">More</span>
        </div>
      </div>
    </div>
  );
}
