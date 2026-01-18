'use client';

import { useWatchlist } from '@/hooks/useWatchlist';
import { useAuth } from '@/providers/auth-provider';
import { Watchlist } from "@/components/dashboard/watchlist";

export default function DashboardPage() {
  const { status } = useAuth();
  const { watchlist, loading, error, refetch } = useWatchlist();

  if (status === 'initializing') {
    return <div className="p-8">Authenticating...</div>;
  }

  if (status !== 'authenticated') {
    return <div className="p-8">Please log in</div>;
  }

  if (loading && !watchlist) {
    return <div className="p-8">Loading watchlist...</div>;
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="bg-red-50 border border-red-200 rounded p-4">
          <h3 className="font-semibold text-red-900">Error</h3>
          <p className="text-sm text-red-700 mt-2">{error.message}</p>
          <button
            onClick={() => refetch()}
            className="mt-4 px-4 py-2 bg-red-600 text-white rounded"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-1 items-start justify-center rounded-lg"
      x-chunk="dashboard-02-chunk-1"
    >
      {watchlist && <Watchlist watchlist={watchlist} />}
    </div>
  );
}
