'use client';

import { useState } from 'react';
import { Copy, Check, Gift } from 'lucide-react';
import { Card, CardLabel } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface ReferralBlockProps {
  referralCode: string | null;
  creditsEarned: number;
}

export function ReferralBlock({ referralCode, creditsEarned }: ReferralBlockProps) {
  const [copied, setCopied] = useState<'link' | 'code' | null>(null);

  if (!referralCode) return null;

  // Use the current origin so the link works whether the user is on the
  // marketing domain, a preview deploy, or localhost during testing.
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const link = `${origin}/signup?ref=${referralCode}`;

  const copy = async (value: string, which: 'link' | 'code') => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(which);
      setTimeout(() => setCopied(null), 1800);
    } catch {
      /* clipboard may be unavailable in some browsers */
    }
  };

  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
        <CardLabel className="m-0">Referrals</CardLabel>
        <span className="font-mono text-2xs tracking-wider uppercase text-accent">
          <Gift size={11} className="inline -mt-0.5 mr-1" />
          {creditsEarned} credit{creditsEarned === 1 ? '' : 's'} earned
        </span>
      </div>

      <p className="text-sm text-fg-dim mb-4">
        Share your link. You get <span className="text-fg font-medium">+3 credits</span> when
        a friend signs up and <span className="text-fg font-medium">+5 more credits</span> when
        they start a subscription.
      </p>

      <div className="space-y-3">
        <div>
          <label className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-1.5 block">
            Your referral link
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              readOnly
              value={link}
              className="flex-1 bg-bg-elev border border-border-1 rounded-sm px-3 py-2 font-mono text-xs text-fg-dim focus:outline-none focus:border-accent transition-colors"
              onFocus={(e) => e.currentTarget.select()}
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => copy(link, 'link')}
              aria-label="Copy link"
            >
              {copied === 'link' ? <Check size={13} /> : <Copy size={13} />}
              {copied === 'link' ? 'Copied' : 'Copy'}
            </Button>
          </div>
        </div>

        <div>
          <label className="font-mono text-2xs tracking-[0.16em] text-fg-mute uppercase mb-1.5 block">
            Or just the code
          </label>
          <div className="flex gap-2 items-center">
            <code className="flex-1 bg-bg-elev border border-border-1 rounded-sm px-3 py-2 font-mono text-sm text-accent tracking-wider">
              {referralCode}
            </code>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => copy(referralCode, 'code')}
              aria-label="Copy code"
            >
              {copied === 'code' ? <Check size={13} /> : <Copy size={13} />}
            </Button>
          </div>
        </div>
      </div>

      <p className="mt-4 text-2xs text-fg-faint font-mono">
        Anti-abuse: signups from an IP that already created an account skip the trial credits
        and don&apos;t trigger referral bonuses.
      </p>
    </Card>
  );
}
