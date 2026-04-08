'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from 'react';
import {
  onIdTokenChanged,
  User as FirebaseUser,
  createUserWithEmailAndPassword,
  signOut as firebaseSignOut,
} from 'firebase/auth';

import { initializeFirebase } from '@/firebase';
import {
  setAuthToken,
  registerUnauthorizedHandler,
} from '@/features/auth/services/token-manager';
import { exchangeTokenForUser } from '@/features/auth/services/auth.service';
import { User } from '@/features/auth/types/auth.types';
import { perf } from '@/lib/performance';

const { auth } = initializeFirebase();

type AuthStatus = 'initializing' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthStateShape {
  status: AuthStatus;
  user: User | null;
  firebaseUser: FirebaseUser | null;
  error: string | null;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  syncWithBackend: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthStateShape | undefined>(undefined);

/**
 * Persist the Firebase ID token into a secure, HTTP-only session cookie via server API.
 * - Server should set a "__session" cookie (SameSite/HttpOnly/Secure) from this endpoint.
 * - We include `credentials: 'same-origin'` so the browser will store cookies set by the server.
 */
async function persistSessionCookie(firebaseUser: FirebaseUser, forceRefresh = false) {
  try {
    const idToken = await firebaseUser.getIdToken(forceRefresh);
    await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ idToken }),
    });
  } catch (err) {
    // Do not break auth flow for cookie persistence errors
    console.warn('[AuthProvider] Failed to persist session cookie:', err);
  }
}

/** Clear the session cookie via server API. */
async function clearSessionCookie() {
  try {
    await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ action: 'clear' }),
    });
  } catch (err) {
    console.warn('[AuthProvider] Failed to clear session cookie:', err);
  }
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  // Internal state without methods (methods are stable functions we attach in Provider value)
  const [authState, setAuthState] = useState<{
    status: AuthStatus;
    user: User | null;
    firebaseUser: FirebaseUser | null;
    error: string | null;
  }>({
    status: 'initializing',
    user: null,
    firebaseUser: null,
    error: null,
  });

  // --- Actions ---

  // Sign up with email and password
  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const firebaseUser = userCredential.user;

      // Persist bearer header for any existing fetch/axios layers (if still used)
      const token = await firebaseUser.getIdToken();
      setAuthToken(token);

      // NEW: persist ID token to secure session cookie for proxy/backend
      await persistSessionCookie(firebaseUser);

      const appUser = await exchangeTokenForUser(firebaseUser);

      setAuthState((prev) => ({
        ...prev,
        status: 'authenticated',
        user: appUser,
        firebaseUser,
        error: null,
      }));
    } catch (error: any) {
      console.error('[AuthProvider] Sign-up error:', error);
      setAuthState((prev) => ({
        ...prev,
        status: 'error',
        error: error?.message || 'Failed to sign up',
      }));
      throw error;
    }
  };

  // Sign out (clears Firebase state, Authorization header, and session cookie)
  const signOut = async () => {
    try {
      await firebaseSignOut(auth);
      setAuthToken(null);

      // NEW: clear the session cookie on logout
      await clearSessionCookie();

      setAuthState((prev) => ({
        ...prev,
        status: 'unauthenticated',
        user: null,
        firebaseUser: null,
        error: null,
      }));
    } catch (error: any) {
      console.error('[AuthProvider] Sign-out error:', error);
      setAuthState((prev) => ({
        ...prev,
        status: 'error',
        error: error?.message || 'Failed to sign out',
      }));
      throw error;
    }
  };

  // Refresh user data from backend (does not de-auth on transient errors)
  const syncWithBackend = async () => {
    try {
      if (authState.firebaseUser) {
        const appUser = await exchangeTokenForUser(authState.firebaseUser);
        setAuthState((prev) => ({ ...prev, user: appUser }));
      }
    } catch (error: any) {
      console.error('[AuthProvider] Sync error:', error);
      // Keep user authenticated; surface error but do not flip global status
      setAuthState((prev) => ({
        ...prev,
        error: 'Failed to sync with backend',
      }));
      throw error;
    }
  };

  // --- Lifecycles & global wiring ---

  // Subscribe once to Firebase auth token changes
  useEffect(() => {
    const unsubscribe = onIdTokenChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        try {
          // Mark perf point if you use it elsewhere
          try { perf.mark?.('auth-token-received'); } catch { }

          // Get current token (non-forced here; change to true if you prefer)
          const token = await firebaseUser.getIdToken();
          setAuthToken(token);

          // NEW: persist/refresh HTTP-only session cookie whenever token changes
          await persistSessionCookie(firebaseUser);

          // Set firebase user and mark authenticated first
          setAuthState((prev) => ({
            ...prev,
            status: 'authenticated',
            firebaseUser,
            error: null,
          }));

          // Fetch app user if we don't have one yet
          if (!authState.user) {
            const appUser = await exchangeTokenForUser(firebaseUser);

            try {
              perf.mark?.('auth-end');
              // Only measure if 'login-start' was previously marked
              perf.measure?.('User Authentication', 'login-start', 'auth-end');
            } catch { }

            setAuthState((prev) => ({
              ...prev,
              status: 'authenticated',
              user: appUser,
              firebaseUser,
              error: null,
            }));
          }
        } catch (error) {
          console.error('[AuthProvider] Error during token exchange:', error);
          setAuthToken(null);

          // Ensure cookie cleared if we fail to sync/validate
          await clearSessionCookie();

          setAuthState((prev) => ({
            ...prev,
            status: 'error',
            user: null,
            firebaseUser: null,
            error: 'Failed to sync with backend.',
          }));
        }
      } else {
        // Signed out or token expired
        setAuthToken(null);

        // NEW: clear cookie when user goes null
        await clearSessionCookie();

        setAuthState((prev) => ({
          ...prev,
          status: 'unauthenticated',
          user: null,
          firebaseUser: null,
          error: null,
        }));
      }
    });

    return () => {
      try { perf.clear?.(); } catch { }
      unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // subscribe once

  // Register a global unauthorized handler so 401/403 from API → real logout
  useEffect(() => {
    registerUnauthorizedHandler(() => {
      // Fire and forget; layout will handle redirect based on status
      signOut().catch(() => { /* swallow */ });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * NEW: Periodically refresh the session cookie so the proxy always has a fresh token.
   * Runs only while authenticated. Uses forceRefresh=true to rotate token proactively.
   */
  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | undefined;

    if (authState.status === 'authenticated') {
      intervalId = setInterval(async () => {
        const user = auth.currentUser;
        if (user) {
          try {
            await persistSessionCookie(user, /* forceRefresh */ true);
          } catch {
            // already logged in persistSessionCookie
          }
        }
      }, 45 * 60 * 1000); // ~45 minutes
    }

    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [authState.status]);

  return (
    <AuthContext.Provider
      value={{
        ...authState,
        signUpWithEmail,
        syncWithBackend,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};