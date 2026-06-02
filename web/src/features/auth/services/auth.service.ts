import { api } from '@/lib/api';
import { User } from '@/features/auth/types/auth.types';

interface TokenExchangeParams {
  email: string;
  displayName?: string | null;
}

/**
 * Exchanges a Supabase session for a StockerPro AppUser profile.
 */
export const exchangeTokenForUser = async (params: TokenExchangeParams): Promise<User> => {
  try {
    console.log('[AuthService] Exchanging session for AppUser...');
    const response = await api.post('/users/sync', {
      email: params.email,
      username: params.displayName || params.email,
    });
    console.log('[AuthService] Token exchange successful.');
    return response.data;
  } catch (error) {
    console.error('[AuthService] Token exchange failed:', error);
    throw error;
  }
};
