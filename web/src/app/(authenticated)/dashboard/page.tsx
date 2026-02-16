'use client';

import { useAuth } from '@/providers/auth-provider';
import { Watchlist } from '@/components/dashboard/watchlist';

/**
 * DashboardPage
 *
 * Phase 1:
 * - Dashboard is the primary surface.
 * - Dashboard renders Watchlist UI shell immediately.
 * - Dashboard does NOT fetch watchlist data.
 * - All watchlist logic is owned by the Watchlist component (Option B).
 */
export default function DashboardPage() {
  const { status } = useAuth();

  if (status === 'initializing') {
    return <div className="p-8">Authenticating...</div>;
  }

  if (status !== 'authenticated') {
    return <div className="p-8">Please log in</div>;
  }

  return (
    <div
      className="flex flex-1 items-start justify-center rounded-lg"
      x-chunk="dashboard-02-chunk-1"
    >
      {/* 
        Phase 1:
        Render Watchlist immediately.
        It will show skeletons first, then hydrate data.
      */}
      <Watchlist />
    </div>
  );
}