import { api } from '@/lib/api';

let unauthorizedHandler: (() => void) | null = null;

/** Allow auth provider to register a sign-out handler for 401/403 */
export const registerUnauthorizedHandler = (fn: () => void) => {
  unauthorizedHandler = fn;
};

export const getUnauthorizedHandler = () => unauthorizedHandler;

/**
 * Manages the authentication token for API requests.
 * @param token The Firebase authentication token, or null to clear it.
 */
export const setAuthToken = (token: string | null) => {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[token-manager] Auth token has been set.');
    }
  } else {
    delete api.defaults.headers.common['Authorization'];
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.debug('[token-manager] Auth token has been cleared.');
    }
  }
};
