import { api } from '@/lib/api';

/**
 * Manages the authentication token for API requests.
 * This function decouples the authentication logic from the API client configuration.
 *
 * @param token The Firebase authentication token, or null to clear it.
 */
export const setAuthToken = (token: string | null) => {
  if (token) {
    // Set the default Authorization header for all subsequent requests.
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    console.log('[token-manager] Auth token has been set.');
  } else {
    // Clear the Authorization header.
    delete api.defaults.headers.common['Authorization'];
    console.log('[token-manager] Auth token has been cleared.');
  }
};
