'use client';

import { useState } from 'react';
import { Link2, X, Copy, Check, Download, FileText, ExternalLink } from 'lucide-react';
import { Card, CardLabel, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError, type ShareResponse } from '@/lib/api';

interface Props {
  slug: string;
  initialToken: string | null;
  publicBaseUrl: string;
}

export function ShareBlock({ slug, initialToken, publicBaseUrl }: Props) {
  const [token, setToken] = useState<string | null>(initialToken);
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const publicUrl = token ? `${publicBaseUrl}/r/${token}` : '';

  const mint = async () => {
    setError(null);
    setPending(true);
    try {
      const r = await apiClient<ShareResponse>(`/v1/investigations/${slug}/share`, { method: 'POST' });
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
      await apiClient(`/v1/investigations/${slug}/share`, { method: 'DELETE' });
      setToken(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not revoke share link.');
    } finally {
      setPending(false);
    }
  };

  const copyLink = async () => {
    if (!publicUrl) return;
    try {
      await navigator.clipboard.writeText(publicUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {/* user can manually copy */}
  };

  return (
    <Card>
      <CardLabel>Share &amp; export</CardLabel>
      {!token ? (
        <>
          <CardTitle>This investigation is private</CardTitle>
          <p className="text-sm text-fg-dim mb-4 max-w-xl">
            Mint a share link to publish a read-only report at a stable URL.
            Recipients see the verdict, cross-links, top flagged commenters,
            and full evidence — no login required, no other investigations
            exposed. Revocable at any time.
          </p>
          <Button onClick={mint} disabled={pending}>
            <Link2 size={14} />
            {pending ? 'Creating…' : 'Create share link'}
          </Button>
        </>
      ) : (
        <>
          <CardTitle>Shareable</CardTitle>
          <p className="text-sm text-fg-dim mb-4">
            Anyone with this link can view the report — verdict, evidence, methodology.
            Recipients can save a PDF or download Markdown/JSON for their own files.
            Revoking instantly disables the link.
          </p>
          <div className="flex items-center gap-2 mb-4">
            <input
              readOnly
              value={publicUrl}
              className="flex-1 h-9 px-3 bg-bg border border-border-2 rounded-sm font-mono text-xs text-fg"
              onFocus={(e) => e.currentTarget.select()}
            />
            <Button variant="secondary" size="sm" onClick={copyLink}>
              {copied ? <><Check size={12} /> Copied</> : <><Copy size={12} /> Copy</>}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <a
              href={`/r/${token}`}
              target="_blank"
              rel="noopener"
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-accent-dim bg-accent/10 text-accent rounded-sm font-mono text-xs tracking-wider uppercase hover:bg-accent/20"
            >
              <ExternalLink size={12} /> Open report
            </a>
            <a
              href={`/r/${token}/markdown?template=evidence`}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
            >
              <FileText size={12} /> Markdown
            </a>
            <a
              href={`/r/${token}/json`}
              className="inline-flex items-center gap-1.5 px-3 h-9 border border-border-2 text-fg-dim rounded-sm font-mono text-xs tracking-wider uppercase hover:text-fg hover:border-border-hot"
            >
              <Download size={12} /> JSON
            </a>
            <Button variant="danger" size="sm" onClick={revoke} disabled={pending}>
              <X size={12} /> Revoke
            </Button>
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
