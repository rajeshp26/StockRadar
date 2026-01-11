import axios from 'axios';

// Create Axios instance
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api/proxy',
  timeout: 10000,
});

// Optional: Add request logging for debugging
api.interceptors.request.use((config) => {
  console.debug('[API Request]', config.method?.toUpperCase(), config.url);
  console.debug('[Auth Header]', config.headers.Authorization ? 'Present' : 'Missing');
  return config;
});

// Optional: Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.warn('[API] Unauthorized - Token may be invalid or expired');
    }
    return Promise.reject(error);
  }
);

export default api;
