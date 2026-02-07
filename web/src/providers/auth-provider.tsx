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

      const token = await firebaseUser.getIdToken();
      setAuthToken(token);

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

  // Sign out (clears Firebase state and Authorization header)
  const signOut = async () => {
    try {
      await firebaseSignOut(auth);
      setAuthToken(null);
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
          try { perf.mark?.('auth-token-received'); } catch {}

          const token = await firebaseUser.getIdToken();
          setAuthToken(token);

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
            } catch {}

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
      try { perf.clear?.(); } catch {}
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