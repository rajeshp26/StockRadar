
'use client';

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
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

interface AuthContextType {
  user: User | null;
  appUser: AppUser | null; // Our custom backend user profile
  loading: boolean;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const { auth } = initializeFirebase();

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [appUser, setAppUser] = useState<AppUser | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // This function performs the background sync with our Python backend
  const syncWithBackend = async () => {
    try {
      console.log('Syncing user profile with Python backend...');
      const response = await api.post<AppUser>('/users/sync');
      setAppUser(response.data);
      console.log('Backend sync successful:', response.data);
    } catch (error) {
      console.error('Backend sync failed:', error);
      // We don't block the app here, just log the error.
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
      
      // If the user just logged in (or we refreshed), trigger the sync in the background
      if (firebaseUser) {
        syncWithBackend();
      } else {
        setAppUser(null);
      }
    });

    return () => unsubscribe();
  }, []);
  
  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(userCredential.user, { displayName: fullName });
    // Calling setUser will trigger the onAuthStateChanged listener, which then calls syncWithBackend
    setUser(auth.currentUser);
  };

  const signInWithEmail = async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
    // onAuthStateChanged will handle the user state update and backend sync
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
