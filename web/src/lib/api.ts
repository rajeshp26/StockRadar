import axios from 'axios';
import { initializeFirebase } from '@/firebase';

const { auth } = initializeFirebase();

/**
 * SECURE API CLIENT:
 * Communicates with the Next.js Proxy Bridge.
 * Automatically attaches the Firebase ID Token for backend verification.
 */
const api = axios.create({
  baseURL: '/api/proxy',
});

api.interceptors.request.use(async (config) => {
  // 1. Get current user
  const user = auth.currentUser;
  
  if (user) {
    // 2. Retrieve fresh ID Token (Firebase handles caching/refresh internally)
    try {
      const token = await user.getIdToken();
      // 3. Attach to Authorization Header
      config.headers.Authorization = `Bearer ${token}`;
    } catch (error) {
      console.error('[SECURITY] Failed to get ID token:', error);
    }
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('[SECURITY] Backend returned 401. Session might be expired.');
    }
    return Promise.reject(error);
  }
);

export default api;
