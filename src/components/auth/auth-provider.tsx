
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
  isSignInWithEmailLink,
  signInWithEmailLink
} from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
import { useRouter } from 'next/navigation';

const { auth } = initializeFirebase();

/**
 * Defines the shape of the authentication context.
 */
interface AuthContextType {
  user: User | null;
  loading: boolean;
  signUpWithEmail: (email: string, password: string, fullName: string) => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  signInWithPasskey: () => Promise<void>;
  signUpWithPasskey: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  signUpWithEmail: async () => {},
  signInWithEmail: async () => {},
  signOut: async () => {},
  signInWithPasskey: async () => { alert('Passkey sign-in not implemented'); },
  signUpWithPasskey: async () => { alert('Passkey sign-up not implemented'); },
});

/**
 * The AuthProvider component manages user authentication state and provides auth-related functions
 * to its children through the AuthContext. It handles user session persistence and redirects.
 * @param {object} props - The component props.
 * @param {ReactNode} props.children - The child components to render within the provider.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      setUser(user);
      setLoading(false);
    });

    // Handle email link sign in
    if (isSignInWithEmailLink(auth, window.location.href)) {
      let email = window.localStorage.getItem('emailForSignIn');
      if (!email) {
        email = window.prompt('Please provide your email for confirmation');
      }
      if(email) {
        signInWithEmailLink(auth, email, window.location.href)
          .then((result) => {
            window.localStorage.removeItem('emailForSignIn');
            setUser(result.user);
            router.push('/dashboard');
          })
          .catch((error) => {
            console.error(error);
          });
      }
    }

    return () => unsubscribe();
  }, [router]);
  
  /**
   * Signs up a new user with email, password, and full name.
   * @param {string} email - The user's email address.
   * @param {string} password - The user's chosen password.
   * @param {string} fullName - The user's full name.
   * @returns {Promise<void>} A promise that resolves when sign-up and profile update are complete.
   */
  const signUpWithEmail = async (email: string, password: string, fullName: string) => {
    const userCredential = await createUserWithEmailAndPassword(auth, email, password);
    await updateProfile(userCredential.user, { displayName: fullName });
    // Manually update the user state to reflect the displayName change immediately
    setUser(auth.currentUser);
  };

  /**
   * Signs in a user with their email and password.
   * @param {string} email - The user's email address.
   * @param {string} password - The user's password.
   * @returns {Promise<void>} A promise that resolves upon successful sign-in.
   */
  const signInWithEmail = async (email: string, password: string) => {
    await signInWithEmailAndPassword(auth, email, password);
  };

  /**
   * Signs out the current user and redirects to the login page.
   * @returns {Promise<void>} A promise that resolves after sign-out and redirection.
   */
  const signOut = async () => {
    await firebaseSignOut(auth);
    router.push('/login');
  };

  /**
   * Placeholder for future passkey sign-in functionality.
   */
  const signInWithPasskey = async () => {
    // Placeholder for passkey sign-in logic
    alert('Passkey sign-in is not yet implemented.');
  };

  /**
   * Placeholder for future passkey sign-up functionality.
   */
  const signUpWithPasskey = async () => {
    // Placeholder for passkey sign-up logic
    alert('Passkey sign-up is not yet implemented.');
  };

  const value = {
    user,
    loading,
    signUpWithEmail,
    signInWithEmail,
    signOut,
    signInWithPasskey,
    signUpWithPasskey,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

/**
 * Custom hook to access the authentication context (user, loading state, and auth functions).
 * @returns {AuthContextType} The authentication context value.
 */
export const useAuth = () => {
  return useContext(AuthContext);
};
