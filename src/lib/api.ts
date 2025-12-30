import axios from 'axios';
import { initializeFirebase } from '@/firebase';

const { auth } = initializeFirebase();

// We are using a relative path to our Next.js API "Bridge".
// This avoids all CORS and Authentication wall issues.
const api = axios.create({
  baseURL: '/api/proxy',
});

api.interceptors.request.use(async (config) => {
  const fullUrl = `${config.baseURL}${config.url}`;
  console.log(`[DEBUG] Frontend: Initiating ${config.method?.toUpperCase()} request to ${fullUrl}`);
  
  const user = auth.currentUser;
  if (user) {
    try {
      const token = await user.getIdToken();
      config.headers.Authorization = `Bearer ${token}`;
      console.log(`[DEBUG] Frontend: Auth token attached.`);
    } catch (error) {
      console.error('[DEBUG] Frontend: Failed to get auth token', error);
    }
  } else {
    console.warn('[DEBUG] Frontend: No user logged in, sending request without token.');
  }
  return config;
});

api.interceptors.response.use(
  (response) => {
    console.log(`[DEBUG] Frontend: Received success from ${response.config.url}. Status: ${response.status}`);
    return response;
  },
  (error) => {
    console.error(`[DEBUG] Frontend: Request to ${error.config?.url} failed. Error:`, error.message);
    if (error.response) {
      console.error(`[DEBUG] Frontend: Error Status: ${error.response.status}. Data:`, error.response.data);
    }
    return Promise.reject(error);
  }
);

export default api;
