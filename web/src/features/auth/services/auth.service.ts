import { api } from '@/lib/api';
import { User } from '@/features/auth/types/auth.types';

interface TokenExchangeParams {
  email: string;
  displayName?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  avatarUrl?: string | null;
}

export const exchangeTokenForUser = async (params: TokenExchangeParams): Promise<User> => {
  try {
    console.log('[AuthService] Exchanging session for AppUser...');
    const response = await api.post('/users/sync', {
      email: params.email,
      username: params.displayName || params.email,
      first_name: params.firstName || null,
      last_name: params.lastName || null,
      avatar_url: params.avatarUrl || null,
    });
    console.log('[AuthService] Token exchange successful.');
    return response.data;
  } catch (error) {
    console.error('[AuthService] Token exchange failed:', error);
    throw error;
  }
};

export const fetchCurrentUser = async (): Promise<User> => {
  const response = await api.get('/users/me');
  return response.data;
};
