'use client';
import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { onIdTokenChanged, User as FirebaseUser } from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
import { setAuthToken } from '@/features/auth/services/token-manager';
import { exchangeTokenForUser } from '@/features/auth/services/auth.service';
import { User } from '@/features/auth/types';
import { perf } from '@/lib/performance'; // Import the performance utility

const { auth } = initializeFirebase();

type AuthStatus = 'initializing' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthState {
  status: AuthStatus;
  user: User | null; 
  firebaseUser: FirebaseUser | null;
  error: string | null;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [authState, setAuthState] = useState<AuthState>({
    status: 'initializing',
    user: null,
    firebaseUser: null,
    error: null,
  });

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
            
            setAuthState({
              status: 'authenticated',
              user: appUser,
              firebaseUser: firebaseUser,
              error: null,
            });
          } else {
            setAuthState(prevState => ({ ...prevState, status: 'authenticated', firebaseUser: firebaseUser }));
          }
        } catch (error) {
          console.error('[AuthProvider] Error during token exchange:', error);
          setAuthState({ status: 'error', user: null, firebaseUser: null, error: 'Failed to sync with backend.' });
        }
      } else {
        setAuthToken(null);
        setAuthState({ status: 'unauthenticated', user: null, firebaseUser: null, error: null });
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
