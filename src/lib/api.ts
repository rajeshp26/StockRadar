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
  
  // The backend no longer verifies JWT tokens, so we don't need to send the Authorization header.
  // The firebase_uid is now expected in the request body for authenticated endpoints.
  
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
