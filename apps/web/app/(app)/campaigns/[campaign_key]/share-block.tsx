'use client';

import { useState } from 'react';
import { Link2, X, Copy, Check, Download, FileText, ExternalLink, Globe } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { apiClient, ApiError, type CampaignShareResponse } from '@/lib/api';

/**
 * Public sharing for a campaign — mint a revocable, token-gated, read-only
 * report at /rc/{token} (no login). Mirrors the investigation share block;
 * the absolute URL is built client-side from the current origin.
 */
export function CampaignShareBlock({
  campaignKey,
  initialToken,
}: {
  campaignKey: string;
  initialToken: string | null;
}) {
  const [token, setToken] = useState<string | null>(initialToken);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const path = token ? `/rc/${token}` : '';
  const absoluteUrl = token && typeof window !== 'undefined'
    ? `${window.location.origin}${path}`
    : path;

  const mint = async () => {
    setError(null);
    setPending(true);
    try {
      const r = await apiClient<CampaignShareResponse>(`/v1/campaigns/${campaignKey}/share`, { method: 'POST' });
      setToken(r.share_token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not create share link.');
    } finally {
      setPending(false);
    }
  };

  const revoke = async () => {
    setError(null);
    setPending(true);
    try {
      await apiClient(`/v1/campaigns/${campaignKey}/share`, { method: 'DELETE' });
      setToken(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not revoke share link.');
    } finally {
      setPending(false);
    }
  };

  const copyLink = async () => {
    if (!absoluteUrl) return;
    try {
      await navigator.clipboard.writeText(absoluteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {/* user can copy manually */}
  };

  return (
    <Card>
      <div className="font-mono text-2xs uppercase tracking-wider text-fg-mute mb-1 flex items-center gap-1.5">
        <Globe size={12} />
        Public report
      </div>
      {!token ? (
        <>
          <p className="text-sm text-fg-dim max-w-xl mb-3">
            Publish a read-only report at a stable URL — verdict, confidence,
            evidence for and against, members, and the recurrence timeline,
            with no login required and no other campaigns exposed. Revocable at
            any time. Built for sharing a finding with an editor, co-investigator,
            or the public.
          </p>
          <button
            onClick={mint}
            disabled={pending}
            className="inline-flex items-center gap-1.5 px-3 h-9 border border-accent-dim bg-accent/10 text-accent rounded-sm font-mono text-xs tracking-wider uppercase hover:bg-accent/20 active:translate-y-px disabled:opacity-50"
          >
            <Link2 size={12} />
            {pending ? 'Creating…' : 'Create public link'}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-fg-dim mb-3">
            Anyone with this link can view the report. Recipients can save a PDF
            or download Markdown / JSON. Revoking disables it instantly.
          </p>
          <div className="flex items-center gap-2 mb-3">
            <input
              readOnly
              value={absoluteUrl}
              className="flex-1 h-9 px-3 bg-bg border border-border-2 rounded-sm font-mono text-xs text-fg"
              onFocus={(e) => e.currentTarget.select()}
            />
            <button
              onClick={copyLink}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
            >
              {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={path}
              target="_blank"
              rel="noopener"
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-accent-dim bg-accent/10 text-accent rounded-sm font-mono text-xs tracking-wider uppercase hover:bg-accent/20 active:translate-y-px"
            >
              <ExternalLink size={12} /> Open report
            </a>
            <a
              href={`${path}/markdown`}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
            >
              <FileText size={12} /> Markdown
            </a>
            <a
              href={`${path}/json`}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
            >
              <Download size={12} /> JSON
            </a>
            <button
              onClick={revoke}
              disabled={pending}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-danger/40 bg-danger/10 text-danger rounded-sm font-mono text-xs tracking-wider uppercase hover:bg-danger/20 active:translate-y-px disabled:opacity-50"
            >
              <X size={12} /> Revoke
            </button>
          </div>
        </>
      )}
      {error && (
        <p className="mt-3 text-xs text-danger bg-danger/10 border border-danger/40 rounded-sm px-3 py-2 font-mono">
          {error}
        </p>
      )}
    </Card>
  );
}
