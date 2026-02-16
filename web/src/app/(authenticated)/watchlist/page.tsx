'use client';

import { Watchlist } from "@/components/dashboard/watchlist";

/**
 * WatchlistPage
 *
 * Phase 1 (Fast First Paint):
 * - Render the Watchlist UI shell immediately.
 * - Watchlist data fetching is owned by the Watchlist feature (Option B).
 * - No dashboard/global preload.
 */
export default function WatchlistPage() {
  return (
    <div className="container mx-auto p-4">
      <Watchlist />
    </div>
  );
}