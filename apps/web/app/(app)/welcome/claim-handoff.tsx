'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowRight, Loader2, TriangleAlert } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ApiError, claimSharedInvestigation } from '@/lib/api';
import { CLAIM_STORAGE_KEY } from '@/app/(auth)/sign-up/[[...sign-up]]/remember-claim';

/**
 * Claim the shared report this account signed up from, then hand off to the scan.
 *
 * Runs exactly once per mount, guarded by a ref rather than by effect deps: React 18 in development
 * mounts effects twice, and the server call, while idempotent, should not be fired twice for nothing.
 *
 * Failure is never a dead end. The claim is a convenience, not the product: if it fails the account
 * still exists with its free credit, so the fallback offers the plain investigate flow instead of
 * stranding a customer who has just signed up on an error page.
 */
export function ClaimHandoff({ tokenFromUrl }: { tokenFromUrl: string }) {
  const router = useRouter();
  const fired = useRef(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;

    // The URL is the happy path; sessionStorage is the backstop for a sign-up that bounced through
    // Clerk's sub-routes and lost the query param on the way.
    let token = tokenFromUrl;
    if (!token) {
      try {
        token = sessionStorage.getItem(CLAIM_STORAGE_KEY) || '';
      } catch {
        token = '';
      }
    }
    if (!token) {
      router.replace('/investigate');
      return;
    }

    void (async () => {
      try {
        const claimed = await claimSharedInvestigation(token);
        try {
          sessionStorage.removeItem(CLAIM_STORAGE_KEY);
        } catch {
          /* nothing to clean up */
        }
        // Straight to the compile step for the same post, carrying the claimed slug so the page can
        // explain where the report went and what the free credit is for.
        const qs = new URLSearchParams({
          url: claimed.input_url,
          claimed: claimed.slug,
        });
        router.replace(`/investigate?${qs.toString()}`);
      } catch (e) {
        // A revoked or unknown token is the expected failure (the owner unshared it between the click
        // and the signup). Nothing is broken for this user, so keep it quiet and offer the normal way in.
        if (!(e instanceof ApiError)) console.error('claim failed', e);
        setFailed(true);
      }
    })();
  }, [tokenFromUrl, router]);

  if (failed) {
    return (
      <div className="max-w-lg mx-auto py-12">
        <Card>
          <div className="flex items-start gap-3">
            <TriangleAlert size={18} className="text-tier-moderate mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="display text-base font-semibold text-fg tracking-tight mb-1.5">
                That report is no longer shared
              </p>
              <p className="text-sm text-fg-dim leading-relaxed mb-5">
                Whoever shared the link has since turned it off, so it could not be saved to your
                account. Your account is set up and your free credit is ready: paste the post you
                want checked and pick the accounts to scan.
              </p>
              <Link href="/investigate">
                <Button>
                  Start a scan
                  <ArrowRight size={14} />
                </Button>
              </Link>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto py-16 text-center" aria-busy>
      <Loader2 size={20} className="animate-spin text-accent mx-auto mb-4" />
      <p className="display text-base font-semibold text-fg tracking-tight mb-1">
        Saving that report to your account
      </p>
      <p className="text-sm text-fg-dim">One moment, then you can scan the rest of the post.</p>
    </div>
  );
}
