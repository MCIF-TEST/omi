import { redirect } from 'next/navigation';

export const metadata = { title: 'Previous investigations — OMISPHERE' };

/**
 * Content DB was merged into Previous investigations.
 * Keep the route so old bookmarks land in the right place.
 */
export default function ContentRedirectPage() {
  redirect('/investigations');
}
