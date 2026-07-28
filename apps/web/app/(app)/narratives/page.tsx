import { notFound } from 'next/navigation';
import { MessageSquareText } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { apiServer } from '@/lib/api-server';
import { type User } from '@/lib/api';

export const dynamic = 'force-dynamic';
export const metadata = { title: 'Narratives · OMISPHERE' };

/**
 * Placeholder for the narrative / campaign detector.
 *
 * ADMIN ONLY, and gated on the SERVER. The coordinated-account surface was removed from the product
 * until a real detection algorithm exists; this exists so the work has a home to land in without
 * showing customers a feature that does nothing. Hiding the nav item alone would not be enough,
 * because the route would still answer to anyone who typed the URL.
 */
export default async function NarrativesPage() {
  let user: User | null = null;
  try {
    user = await apiServer<User>('/v1/auth/me');
  } catch {
    user = null;
  }
  if (!user?.is_admin) notFound();

  return (
    <div className="space-y-6 max-w-3xl">
      <header className="aurora relative overflow-hidden rounded-2xl border border-border-1 bg-bg-elev px-6 py-6 md:px-7">
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/50 to-transparent" />
        <div className="relative">
          <span className="section-label">Coordination · Admin preview</span>
          <h1 className="display text-2xl font-semibold tracking-tight mt-3">Narratives</h1>
          <p className="text-sm text-fg-dim mt-1.5 max-w-2xl leading-relaxed">
            Coming soon: narrative / campaign detector.
          </p>
        </div>
      </header>

      <Card>
        <div className="flex gap-4">
          <span className="shrink-0 grid place-items-center w-10 h-10 rounded-lg border border-border-2 bg-bg-elev-2 text-fg-mute">
            <MessageSquareText size={18} />
          </span>
          <div className="min-w-0 space-y-2">
            <p className="text-sm text-fg">
              Not built yet. This page is visible to admins only.
            </p>
            <p className="text-sm text-fg-dim leading-relaxed">
              The previous coordinated-account surface was removed rather than left running,
              because it presented clusters the engine had not earned the right to call
              coordinated. The detection work lands here when the algorithm exists.
            </p>
            <p className="font-mono text-2xs text-fg-mute uppercase tracking-wider pt-1">
              Status: in design
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
