'use client';

import { useAuth } from '@/providers/auth-provider';
import { Watchlist } from '@/components/dashboard/watchlist';

export default function DashboardPage() {
  const { status } = useAuth();

  if (status === 'initializing') {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="relative flex items-center justify-center">
          <div className="h-12 w-12 rounded-full border border-white/10" />
          <div className="absolute h-12 w-12 animate-spin rounded-full border-t-2 border-indigo-500" />
        </div>
      </div>
    );
  }

  if (status !== 'authenticated') {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-white/40">Please log in to continue.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 items-start justify-center">
      <Watchlist />
    </div>
  );
}