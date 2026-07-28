import { notFound } from 'next/navigation';
import { getCurrentUser } from '@/lib/auth';
import { FeedbackQueue } from './feedback-queue';

export const metadata = { title: 'Feedback queue. OMISPHERE' };
export const dynamic = 'force-dynamic';

// Admin-only: the searchable feedback queue. Non-admins can't see it exists.
export default async function FeedbackAdminPage() {
  const user = await getCurrentUser();
  if (!user?.is_admin) notFound();
  return (
    <div className="space-y-5 -mt-2">
      <header>
        <span className="section-label">Admin · Feedback</span>
        <h1 className="display text-2xl font-semibold text-fg tracking-tight mt-2">Feedback queue</h1>
        <p className="text-sm text-fg-mute mt-1">Everything users have sent. Search by keyword or email.</p>
      </header>
      <FeedbackQueue />
    </div>
  );
}
