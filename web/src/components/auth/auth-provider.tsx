
'use client';

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { 
  getAuth, 
  onAuthStateChanged, 
  User, 
  createUserWithEmailAndPassword, 
  signInWithEmailAndPassword, 
  signOut as firebaseSignOut,
  updateProfile,
} from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
import { useRouter } from 'next/navigation';
import api from '@/lib/api';

// --- Types for our Backend User ---
export interface AppUser {
  user_id: number;
  email: string;
  username: string;
  default_watchlist_id: number | null;
}

// Intermediate type for the user profile from the /users/sync endpoint
export interface UserProfile {
    user_id: number;
    email: string;
    username: string;
}

interface AuthContextType {
  user: User | null;
  appUser: AppUser | null; // Our custom backend user profile
  loading: boolean;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  syncWithBackend: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const { auth } = initializeFirebase();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [appUser, setAppUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // This function performs the background sync with our Python backend
  const syncWithBackend = useCallback(async () => {
    if (!auth.currentUser) {
        console.warn('syncWithBackend called without a logged-in user.');
        return;
    }
    const currentUser = auth.currentUser;
    try {
      // Step 1: Sync user profile
      console.log('Syncing user profile with Python backend...');
      // SECURITY: firebase_uid is retrieved from the JWT token on the backend
      const profileResponse = await api.post<UserProfile>('/users/sync', {
        email: currentUser.email,
        username: currentUser.displayName || currentUser.email?.split('@')[0] || 'User',
      });
      const userProfile = profileResponse.data;
      console.log('Backend user sync successful:', userProfile);

      // Step 2: Get or create the default watchlist using the new consolidated endpoint
      console.log('Ensuring default watchlist exists...');
      const watchlistResponse = await api.post<{ watchlist_id: number, name: string, is_default: boolean, items: any[], stocks: any[] }>('/watchlists/default-with-items', {
        firebase_uid: currentUser.uid,
      });
      // Extract the default_watchlist_id from the response
      const defaultWatchlistId = watchlistResponse.data.watchlist_id;
      console.log('Default watchlist ID:', defaultWatchlistId);

      // Step 3: Combine into the final AppUser object
      setAppUser({
        ...userProfile,
        default_watchlist_id: defaultWatchlistId,
      });

    } catch (error) {
      console.error('Backend sync failed:', error);
      // We don't block the app here, just log the error.
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
      // We no longer automatically sync here. Sync is now triggered explicitly.
      if (!firebaseUser) {
        setAppUser(null);
      }
    });

    return () => unsubscribe();
  }, []);
  
  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(userCredential.user, { displayName: fullName });
    setUser(auth.currentUser); // Update React state immediately
    // syncWithBackend will be called explicitly from the form now.
  };

  const signInWithEmail = async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    // syncWithBackend will be called explicitly from the form now.
  };

  const signOut = async () => {
    await firebaseSignOut(auth);
    setAppUser(null);
    router.push('/login');
  };

  const value = {
    user,
    appUser,
    loading,
    signUpWithEmail,
    signInWithEmail,
    signOut,
    syncWithBackend,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
