
import { api } from '@/lib/api';

/**
 * Fetches the default watchlist for the authenticated user.
 */
export const getDefaultWatchlist = async () => {
  try {
    console.log('[watchlist-service] Fetching default watchlist...');

    const response = await api.post(
      '/watchlists/default-with-items',
      {},
      { timeout: 10000 }
    );

    console.log('[watchlist-service] Successfully fetched watchlist:', {
      id: response.data.watchlist_id,
      name: response.data.name,
      itemCount: response.data.stocks?.length || 0,
    });

    return response.data;

  } catch (error: any) {
    const errorDetails = {
      status: error.response?.status,
      statusText: error.response?.statusText,
      message: error.message,
      endpoint: '/watchlists/default-with-items',
      timestamp: new Date().toISOString(),
    };
    console.error('[watchlist-service] Failed to fetch watchlist:', errorDetails);

    if (error.response?.status === 401) {
      throw new Error('Authentication failed. Please log in again.');
    } else if (error.response?.status === 404) {
      throw new Error('No default watchlist found for your account.');
    } else if (error.response?.status === 500) {
      throw new Error('Server error while fetching watchlist. Please try again.');
    } else if (error.code === 'ECONNABORTED') {
      throw new Error('Request timeout. The server took too long to respond.');
    } else {
      throw new Error(error.message || 'Failed to fetch watchlist');
    }
  }
};

/**
 * Creates a new watchlist for the authenticated user.
 */
export const createWatchlist = async (name: string) => {
  try {
    console.log('[watchlist-service] Creating watchlist:', { name });

    const response = await api.post('/watchlists', { name });

    console.log('[watchlist-service] Successfully created watchlist:', response.data);
    return response.data;

  } catch (error: any) {
    console.error('[watchlist-service] Failed to create watchlist:', {
      status: error.response?.status,
      message: error.message,
    });
    throw error;
  }
};

/**
 * Adds a stock to a watchlist.
 */
export const addStockToWatchlist = async (
  watchlistId: string,
  symbol: string
) => {
  try {
    console.log('[watchlist-service] Adding stock to watchlist:', {
      watchlistId,
      symbol,
    });

    const response = await api.post(
      `/watchlists/${watchlistId}/items`,
      { symbol }
    );

    console.log('[watchlist-service] Successfully added stock:', {
      watchlistId,
      symbol,
    });

    return response.data;

  } catch (error: any) {
    console.error('[watchlist-service] Failed to add stock:', {
      watchlistId,
      symbol,
      status: error.response?.status,
      message: error.message,
    });
    throw error;
  }
};

/**
 * Removes a stock from a watchlist.
 */
export const removeStockFromWatchlist = async (
  watchlistId: string,
  itemId: string
) => {
  try {
    console.log('[watchlist-service] Removing stock from watchlist:', {
      watchlistId,
      itemId,
    });

    const response = await api.delete(
      `/watchlists/${watchlistId}/items/${itemId}`
    );

    console.log('[watchlist-service] Successfully removed stock:', {
      watchlistId,
      itemId,
    });

    return response.data;

  } catch (error: any) {
    console.error('[watchlist-service] Failed to remove stock:', {
      watchlistId,
      itemId,
      status: error.response?.status,
      message: error.message,
    });
    throw error;
  }
};
