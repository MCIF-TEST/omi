'use client';

import { useState, type FormEvent } from 'react';
import { Plus, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input, Label } from '@/components/ui/input';
import { apiClient, ApiError, type WatchlistOut } from '@/lib/api';

interface Props {
  onAdded: (w: WatchlistOut) => void;
}

const TIERS = [
  { value: 'moderate', label: 'Moderate+' },
  { value: 'elevated', label: 'Elevated+' },
  { value: 'high', label: 'High only' },
];

export function WatchlistForm({ onAdded }: Props) {
  const [targetId, setTargetId] = useState('');
  const [label, setLabel] = useState('');
  const [platform, setPlatform] = useState('youtube');
  const [threshold, setThreshold] = useState('moderate');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!targetId.trim()) return;
    setError(null);
    setPending(true);
    try {
      const w = await apiClient<WatchlistOut>('/v1/watchlists', {
        method: 'POST',
        body: JSON.stringify({
          kind: 'channel',
          target_id: targetId.trim(),
          platform,
          label: label.trim() || targetId.trim(),
          alert_threshold_tier: threshold,
        }),
      });
      onAdded(w);
      setTargetId('');
      setLabel('');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Failed to add watchlist.');
    } finally {
      setPending(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="grid grid-cols-1 sm:grid-cols-[auto_1fr_1fr_auto_auto] gap-3 items-end">
      <div>
        <Label htmlFor="wl-platform">Platform</Label>
        <select
          id="wl-platform"
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="w-full h-10 px-3 bg-bg-elev border border-border-2 rounded-sm font-mono text-sm text-fg focus:border-accent-dim focus:outline-none"
        >
          <option value="youtube">YouTube</option>
          <option value="x">X</option>
        </select>
      </div>
      <div>
        <Label htmlFor="wl-target">{platform === 'x' ? 'Handle / ID' : 'Channel ID'}</Label>
        <Input
          id="wl-target"
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          placeholder={platform === 'x' ? '@handle' : 'UC… or @handle'}
        />
      </div>
      <div>
        <Label htmlFor="wl-label">Label (optional)</Label>
        <Input
          id="wl-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="What to call this"
        />
      </div>
      <div>
        <Label htmlFor="wl-threshold">Alert at</Label>
        <select
          id="wl-threshold"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          className="w-full h-10 px-3 bg-bg-elev border border-border-2 rounded-sm font-mono text-sm text-fg focus:border-accent-dim focus:outline-none"
        >
          {TIERS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>
      <Button type="submit" disabled={pending || !targetId.trim()}>
        {pending ? <><Loader2 size={14} className="animate-spin" /> Adding…</> : <><Plus size={14} /> Add</>}
      </Button>
      {error && (
        <p className="sm:col-span-5 text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          {error}
        </p>
      )}
    </form>
  );
}
