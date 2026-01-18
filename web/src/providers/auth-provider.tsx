'use client';
import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { onIdTokenChanged, User as FirebaseUser, createUserWithEmailAndPassword, signOut as firebaseSignOut } from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
import { setAuthToken } from '@/features/auth/services/token-manager';
import { exchangeTokenForUser } from '@/features/auth/services/auth.service';
import { User } from '@/features/auth/types/auth.types';
import { perf } from '@/lib/performance';

const { auth } = initializeFirebase();

type AuthStatus = 'initializing' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthState {
  status: AuthStatus;
  user: User | null;
  firebaseUser: FirebaseUser | null;
  error: string | null;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  syncWithBackend: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [authState, setAuthState] = useState<AuthState>({
    status: 'initializing',
    user: null,
    firebaseUser: null,
    error: null,
    signUpWithEmail: async () => {},
    syncWithBackend: async () => {},
    signOut: async () => {},
  });

  // Sign up with email and password
  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const firebaseUser = userCredential.user;

      // Get the ID token
      const token = await firebaseUser.getIdToken();
      setAuthToken(token);

      // Exchange token for app user
      const appUser = await exchangeTokenForUser(firebaseUser);

      setAuthState(prevState => ({
        ...prevState,
        status: 'authenticated',
        user: appUser,
        firebaseUser: firebaseUser,
        error: null,
      }));
    } catch (error: any) {
      console.error('[AuthProvider] Sign-up error:', error);
      setAuthState(prevState => ({
        ...prevState,
        status: 'error',
        error: error.message || 'Failed to sign up',
      }));
      throw error;
    }
  };

  // Sign out
  const signOut = async () => {
    try {
      await firebaseSignOut(auth);
      setAuthToken(null);
      setAuthState(prevState => ({
        ...prevState,
        status: 'unauthenticated',
        user: null,
        firebaseUser: null,
        error: null,
      }));
    } catch (error: any) {
      console.error('[AuthProvider] Sign-out error:', error);
      setAuthState(prevState => ({
        ...prevState,
        status: 'error',
        error: error.message || 'Failed to sign out',
      }));
      throw error;
    }
  };

  // Sync with backend (refresh user data)
  const syncWithBackend = async () => {
    try {
      if (authState.firebaseUser) {
        const appUser = await exchangeTokenForUser(authState.firebaseUser);
        setAuthState(prevState => ({
          ...prevState,
          user: appUser,
        }));
      }
    } catch (error: any) {
      console.error('[AuthProvider] Sync error:', error);
      setAuthState(prevState => ({
        ...prevState,
        status: 'error',
        error: 'Failed to sync with backend',
      }));
      throw error;
    }
  };

  useEffect(() => {
    const unsubscribe = onIdTokenChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        perf.mark('auth-token-received');
        try {
          const token = await firebaseUser.getIdToken();
          setAuthToken(token);
          if (!authState.user) {
            const appUser = await exchangeTokenForUser(firebaseUser);
            perf.mark('auth-end');
            perf.measure('User Authentication', 'login-start', 'auth-end');

            setAuthState(prevState => ({
              ...prevState,
              status: 'authenticated',
              user: appUser,
              firebaseUser: firebaseUser,
              error: null,
            }));
          } else {
            setAuthState(prevState => ({
              ...prevState,
              status: 'authenticated',
              firebaseUser: firebaseUser,
            }));
          }
        } catch (error) {
          console.error('[AuthProvider] Error during token exchange:', error);
          setAuthState(prevState => ({
            ...prevState,
            status: 'error',
            user: null,
            firebaseUser: null,
            error: 'Failed to sync with backend.',
          }));
        }
      } else {
        setAuthToken(null);
        setAuthState(prevState => ({
          ...prevState,
          status: 'unauthenticated',
          user: null,
          firebaseUser: null,
          error: null,
        }));
      }
    });

    return () => {
      unsubscribe();
      perf.clear();
    };
  }, [authState.user]);

  return <AuthContext.Provider value={authState}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};