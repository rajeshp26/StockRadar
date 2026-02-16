'use client';

import { useAuth } from '@/providers/auth-provider';
import { useEffect, useState, useCallback, useRef } from 'react';
import { getDefaultWatchlist } from '@/services/watchlist.service';

interface UseWatchlistReturn {
  watchlist: any | null;
  loading: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

/**
 * @deprecated
 * DO NOT USE.
 *
 * This legacy hook eagerly fetches the watchlist and opens SSE.
 * It is intentionally deprecated in favor of:
 *
 *   features/watchlists/hooks/useWatchlist
 *
 * Importing this hook outside the Watchlist feature is forbidden.
 */
export function useWatchlist(): UseWatchlistReturn {
  if (process.env.NODE_ENV !== 'production') {
    throw new Error(
      '[Deprecated] web/src/hooks/useWatchlist.ts is no longer allowed. ' +
      'Use features/watchlists/hooks/useWatchlist instead.'
    );
  }
  const { status } = useAuth();
  const [watchlist, setWatchlist] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Track retry attempts to avoid infinite loops
  const retryCountRef = useRef(0);
  const maxRetries = 2;
  const retryDelayMs = 2000;
  const hasInitializedRef = useRef(false);

  /**
   * Fetches the default watchlist from the API.
   * Only executes when user is fully authenticated.
   */
  const fetchWatchlist = useCallback(async () => {
    // Guard: Don't fetch until authentication is complete
    // IMPORTANT: status === 'authenticated' is the primary guard
    if (status !== 'authenticated') {
      console.log('[useWatchlist] Auth not ready. Status:', status);
      return;
    }

    // Guard: Don't fetch if already loading
    if (loading) {
      console.log('[useWatchlist] Already loading, skipping duplicate request');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      console.log('[useWatchlist] Fetching watchlist. Status:', status);
      const data = await getDefaultWatchlist();

      setWatchlist(data);
      retryCountRef.current = 0; // Reset retry count on success
      console.log('[useWatchlist] Watchlist loaded successfully');
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('[useWatchlist] Failed to fetch watchlist:', error.message);
      setError(error);

      // Implement retry logic
      if (retryCountRef.current < maxRetries) {
        retryCountRef.current += 1;
        console.log(
          `[useWatchlist] Retrying in ${retryDelayMs}ms (attempt ${retryCountRef.current}/${maxRetries})`
        );

        const timeoutId = setTimeout(() => {
          console.log('[useWatchlist] Executing retry...');
          fetchWatchlist();
        }, retryDelayMs);

        // Cleanup timeout if component unmounts
        return () => clearTimeout(timeoutId);
      } else {
        console.error('[useWatchlist] Max retries reached. Giving up.');
      }
    } finally {
      setLoading(false);
    }
  }, [status, loading]);

  /**
   * Effect: Trigger fetch when authentication state changes.
   * Only trigger ONCE when status becomes 'authenticated'
   */
  useEffect(() => {
    // Skip if already fetched
    if (hasInitializedRef.current) {
      return;
    }

    // Only fetch when authenticated
    if (status === 'authenticated') {
      hasInitializedRef.current = true;
      fetchWatchlist();
    }
  }, [status, fetchWatchlist]);

  /**
   * Public refetch method for manual refresh (e.g., retry button).
   * Resets retry counter to allow fresh retry attempts.
   */
  const refetch = useCallback(async () => {
    retryCountRef.current = 0; // Reset retry counter
    await fetchWatchlist();
  }, [fetchWatchlist]);

  return {
    watchlist,
    loading,
    error,
    refetch,
  };
}
