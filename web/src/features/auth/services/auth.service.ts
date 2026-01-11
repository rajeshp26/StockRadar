import { api } from '@/lib/api';
import { User } from '@/features/auth/types';
import { User as FirebaseUser } from 'firebase/auth';

/**
 * Exchanges a Firebase token for a StockerPro AppUser profile.
 * This is the crucial step that translates a Firebase user into an application-specific user.
 */
export const exchangeTokenForUser = async (firebaseUser: FirebaseUser): Promise<User> => {
  try {
    console.log('[AuthService] Exchanging Firebase token for AppUser...');
    const response = await api.post('/users/sync', {
      email: firebaseUser.email,
      username: firebaseUser.displayName || firebaseUser.email,
    });
    console.log('[AuthService] Token exchange successful.');
    return response.data;
  } catch (error) {
    console.error('[AuthService] Token exchange failed:', error);
    throw error; // Re-throw to be caught by the calling function
  }
};
