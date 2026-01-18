import axios from 'axios';

// Create axios instance with base URL for backend API
// In development: uses Next.js proxy at /api/proxy (configured in app/api/proxy/[...path]/route.ts)
// In production: uses direct backend URL from environment or relative path
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || '/api/proxy',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for logging and auth token injection
api.interceptors.request.use((config) => {
  console.log(`[API] ${config.method?.toUpperCase()} ${config.baseURL}${config.url}`);
  return config;
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.error('[API] Unauthorized - clearing auth');
      // Handle unauthorized error (e.g., redirect to login)
    }
    return Promise.reject(error);
  }
);