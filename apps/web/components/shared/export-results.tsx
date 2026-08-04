'use client';

import { useMemo, useState } from 'react';
import { Check, Copy, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  buildExportRows,
  exportFilename,
  toCsv,
  toTsv,
  type ScannedAccount,
} from '@/lib/investigation-export';
import type { CommenterAssessment } from '@/lib/api';

interface Props {
  slug: string;
  createdAt?: string;
  /** Every account the scan scored, projected server-side (see scannedAccountsFrom). */
  scanned: ScannedAccount[];
  /** The analyst's per-account reads, already filtered for this viewer by the API. */
  reads?: CommenterAssessment[];
}

/**
 * Get the whole investigation out of the page: a CSV file, or the same table on the clipboard.
 *
 * Two buttons rather than one because they serve different next steps, and picking one for the user
 * would be wrong half the time. Copy is for pasting straight into a spreadsheet or a doc, which is
 * what someone writing up a finding does. Download is for keeping the file, which is what someone
 * building a case does.
 *
 * The rows are assembled on the client from data the page already has, so neither button issues a
 * request. That also means the export contains exactly what the viewer is permitted to see: the
 * per-account reads arrive already filtered by the API's viewer gate, and the columns follow the
 * data rather than a second judgement made here.
 */
export function ExportResults({ slug, createdAt, scanned, reads }: Props) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);

  // Memoised because the panel that hosts this re-renders on every analyst poll, once every 2.5s for
  // up to ten minutes, and the join runs over every account in the investigation.
  const rows = useMemo(() => buildExportRows(scanned, reads), [scanned, reads]);
  if (rows.length === 0) return null;

  const copy = async () => {
    setFailed(null);
    const text = toTsv(rows);
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // navigator.clipboard is undefined outside a secure context and can be refused by permission
      // policy. The deprecated path still works in both cases, and silently doing nothing when
      // someone clicks Copy is the one outcome worth avoiding.
      if (!legacyCopy(text)) {
        setFailed('Could not reach the clipboard. Use Download CSV instead.');
        return;
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }
  };

  const download = () => {
    setFailed(null);
    const blob = new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = exportFilename(slug, createdAt);
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Revoked on the next tick, not immediately: Safari cancels an in-flight download when the
    // object URL is released in the same frame as the click.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return (
    <div className="flex flex-col items-start gap-1 sm:items-end">
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={copy} title="Copy all accounts as a table">
          {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy table</>}
        </Button>
        <Button variant="secondary" size="sm" onClick={download} title="Download all accounts as CSV">
          <Download size={12} /> CSV
        </Button>
      </div>
      <p className="font-mono text-2xs text-fg-mute" aria-live="polite">
        {copied
          ? `${rows.length} row${rows.length === 1 ? '' : 's'} copied, paste into a spreadsheet`
          : `${rows.length} account${rows.length === 1 ? '' : 's'}, every one this scan scored`}
      </p>
      {failed && <p className="font-mono text-2xs text-danger">{failed}</p>}
    </div>
  );
}

/** document.execCommand('copy') over an off-screen textarea. Deprecated, and still the only thing
 *  that works on an insecure origin or where the async Clipboard API is blocked by policy. */
function legacyCopy(text: string): boolean {
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    // Off-screen rather than display:none, which is not selectable, and never below 16px: a
    // focusable control under 16px is what makes iOS Safari zoom the whole page and stay zoomed.
    ta.style.cssText = 'position:fixed;top:0;left:-9999px;font-size:16px;';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return ok;
  } catch {
    return false;
  }
}
