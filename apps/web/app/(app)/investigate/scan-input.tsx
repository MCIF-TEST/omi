'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { Search, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const VIDEO_RE = /(?:v=|\/shorts\/|youtu\.be\/|\/embed\/|\/v\/)([A-Za-z0-9_-]{11})|^([A-Za-z0-9_-]{11})$/;
const CHANNEL_RE = /^(UC[A-Za-z0-9_-]{22})$|youtube\.com\/channel\/(UC[A-Za-z0-9_-]{22})|youtube\.com\/@([A-Za-z0-9_.\-]+)|^@([A-Za-z0-9_.\-]+)$|youtube\.com\/(?:c|user)\/([A-Za-z0-9_.\-]+)/;

function classify(raw: string): { kind: 'video' | 'channel' | 'unknown' | 'idle'; label: string } {
  const s = raw.trim();
  if (!s) return { kind: 'idle', label: 'Paste a YouTube video or channel URL' };
  if (VIDEO_RE.test(s)) return { kind: 'video', label: 'YouTube video detected — will scan every commenter + coordination' };
  if (CHANNEL_RE.test(s)) return { kind: 'channel', label: 'YouTube channel detected — will deep-scan account history + fingerprint' };
  return { kind: 'unknown', label: 'Unrecognized link. Paste a YouTube video or channel URL.' };
}

interface Props {
  initialUrl?: string;
  pending: boolean;
  batchSize: number;
  onBatchSizeChange: (n: number) => void;
  onScan: (url: string) => void;
}

export function ScanInput({ initialUrl = '', pending, batchSize, onBatchSizeChange, onScan }: Props) {
  const [url, setUrl] = useState(initialUrl);
  const [c, setC] = useState(() => classify(initialUrl));

  useEffect(() => setC(classify(url)), [url]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (c.kind === 'unknown' || c.kind === 'idle' || pending) return;
    onScan(url.trim());
  };

  const borderColor =
    c.kind === 'video'   ? 'border-accent focus:shadow-glow-sm' :
    c.kind === 'channel' ? 'border-tier-elevated/60' :
    c.kind === 'unknown' ? 'border-danger/60' :
    'border-border-2';

  return (
    <form onSubmit={onSubmit} className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-3">
        <Input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a YouTube video or channel URL…"
          className={`h-12 text-base ${borderColor} flex-1`}
          autoFocus
        />
        <Button
          type="submit"
          size="lg"
          disabled={pending || c.kind === 'unknown' || c.kind === 'idle'}
          className="h-12 px-6"
        >
          {pending ? (
            <>
              <Loader2 size={16} className="animate-spin" />
              Scanning…
            </>
          ) : (
            <>
              <Search size={16} />
              Run scan
            </>
          )}
        </Button>
      </div>
      <div className="flex items-center justify-between gap-4 flex-wrap text-xs">
        <span className={`font-mono uppercase tracking-wider ${
          c.kind === 'video' ? 'text-accent' :
          c.kind === 'channel' ? 'text-tier-elevated' :
          c.kind === 'unknown' ? 'text-danger' :
          'text-fg-mute'
        }`}>
          ▸ {c.label}
        </span>
        <label className="flex items-center gap-2 font-mono text-2xs tracking-wider text-fg-mute uppercase">
          <span>Batch:</span>
          <input
            type="range"
            min={25} max={500} step={25} value={batchSize}
            onChange={(e) => onBatchSizeChange(parseInt(e.target.value, 10))}
            className="accent-accent w-24"
          />
          <span className="text-fg mono w-10 text-right">{batchSize}</span>
        </label>
      </div>
    </form>
  );
}
