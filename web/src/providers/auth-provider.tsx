'use client';

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from 'react';
import { Session, AuthError } from '@supabase/supabase-js';

import { createClient } from '@/lib/supabase';
import {
  registerUnauthorizedHandler,
} from '@/features/auth/services/token-manager';
import { exchangeTokenForUser } from '@/features/auth/services/auth.service';
import { User } from '@/features/auth/types/auth.types';
import { perf } from '@/lib/performance';

const supabase = createClient();

type AuthStatus = 'initializing' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthStateShape {
  status: AuthStatus;
  user: User | null;
  session: Session | null;
  error: string | null;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  syncWithBackend: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthStateShape | undefined>(undefined);

/**
 * Persist the Supabase access token into a secure, HTTP-only session cookie via server API.
 */
async function persistSessionCookie(accessToken: string) {
  try {
    await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ accessToken }),
    });
  } catch (err) {
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
  const [authState, setAuthState] = useState<{
    status: AuthStatus;
    user: User | null;
    session: Session | null;
    error: string | null;
  }>({
    status: 'initializing',
    user: null,
    session: null,
    error: null,
  });

  // --- Actions ---

  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { display_name: fullName || email } },
      });

      if (error) throw error;
      if (!data.session) {
        throw new Error('Sign-up succeeded but no session returned (email confirmation may be required)');
      }

      const appUser = await exchangeTokenForUser({
        email: data.user?.email ?? email,
        displayName: fullName || email,
      });

      setAuthState((prev) => ({
        ...prev,
        status: 'authenticated',
        user: appUser,
        session: data.session,
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

  const signOut = async () => {
    try {
      await supabase.auth.signOut();
      await clearSessionCookie();

      setAuthState((prev) => ({
        ...prev,
        status: 'unauthenticated',
        user: null,
        session: null,
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

  const syncWithBackend = async () => {
    try {
      if (authState.session) {
        const appUser = await exchangeTokenForUser({
          email: authState.session.user.email ?? '',
          displayName: authState.session.user.user_metadata?.display_name ?? null,
        });
        setAuthState((prev) => ({ ...prev, user: appUser }));
      }
    } catch (error: any) {
      console.error('[AuthProvider] Sync error:', error);
      setAuthState((prev) => ({
        ...prev,
        error: 'Failed to sync with backend',
      }));
      throw error;
    }
  };

  // --- Lifecycles & global wiring ---

  useEffect(() => {
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {

        if (session) {
          try {
            try { perf.mark?.('auth-token-received'); } catch { }

            await persistSessionCookie(session.access_token);

            setAuthState((prev) => ({
              ...prev,
              status: 'authenticated',
              session,
              error: null,
            }));

            // Background-sync user profile — failure must NOT revert login.
            // The session cookie is already set; the user is authenticated.
            // If the backend is down or returns an error, log and continue.
            exchangeTokenForUser({
              email: session.user.email ?? '',
              displayName: session.user.user_metadata?.display_name ?? null,
            }).then((appUser) => {
              try {
                perf.mark?.('auth-end');
                perf.measure?.('User Authentication', 'login-start', 'auth-end');
              } catch { }

              setAuthState((prev) => ({
                ...prev,
                status: 'authenticated',
                user: appUser,
                session,
                error: null,
              }));
            }).catch((err) => {
              console.warn('[AuthProvider] Profile sync failed (non-fatal):', err);
            });
          } catch (error) {
            console.error('[AuthProvider] Error during session handling:', error);
            await clearSessionCookie();

            setAuthState((prev) => ({
              ...prev,
              status: 'error',
              user: null,
              session: null,
              error: 'Authentication failed.',
            }));
          }
        } else {
          await clearSessionCookie();

          setAuthState((prev) => ({
            ...prev,
            status: 'unauthenticated',
            user: null,
            session: null,
            error: null,
          }));
        }
      }
    );

    return () => {
      try { perf.clear?.(); } catch { }
      subscription.unsubscribe();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    registerUnauthorizedHandler(() => {
      signOut().catch(() => { /* swallow */ });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | undefined;

    if (authState.status === 'authenticated') {
      intervalId = setInterval(async () => {
        const { data: { session } } = await supabase.auth.getSession();
        if (session) {
          try {
            await persistSessionCookie(session.access_token);
          } catch {
            // already logged in persistSessionCookie
          }
        }
      }, 45 * 60 * 1000);
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
