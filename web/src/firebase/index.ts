'use client';

import { firebaseConfig } from '@/firebase/config';
import { initializeApp, getApps, getApp, FirebaseApp } from 'firebase/app';
import { getAuth, setPersistence, browserLocalPersistence } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore'

// IMPORTANT: DO NOT MODIFY THIS FUNCTION
export function initializeFirebase() {
  if (!getApps().length) {
    // Important! initializeApp() is called without any arguments because Firebase App Hosting
    // integrates with the initializeApp() function to provide the environment variables needed to
    // populate the FirebaseOptions in production. It is critical that we attempt to call initializeApp()
    // without arguments.
    let firebaseApp;
    try {
      // Attempt to initialize via Firebase App Hosting environment variables
      firebaseApp = initializeApp();
    } catch (e) {
      // Only warn in production because it's normal to use the firebaseConfig to initialize
      // during development
      // if (process.env.NODE_ENV === "production") {
      //   console.warn('Automatic initialization failed. Falling back to firebase config object.', e);
      // }
      firebaseApp = initializeApp(firebaseConfig);
    }

    const sdks = getSdks(firebaseApp);
    // Fire-and-forget: set persistence to localStorage (synchronous) instead of IndexedDB (async)
    // to eliminate race conditions where onIdTokenChanged fires null before
    // IndexedDB resolves the persisted session on page load.
    setPersistence(sdks.auth, browserLocalPersistence).catch(() => {});
    return sdks;
  }

  // If already initialized, return the SDKs with the already initialized App
  const sdks = getSdks(getApp());
  setPersistence(sdks.auth, browserLocalPersistence).catch(() => {});
  return sdks;
}

export function getSdks(firebaseApp: FirebaseApp) {
  return {
    firebaseApp,
    auth: getAuth(firebaseApp),
    firestore: getFirestore(firebaseApp)
  };
}

export * from './provider';
export * from './client-provider';
export * from './firestore/use-collection';
export * from './firestore/use-doc';
export * from './non-blocking-updates';
export * from './non-blocking-login';
export * from './errors';
export * from './error-emitter';
