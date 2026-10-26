import { initializeApp, getApps, getApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';

// Default configuration ensures Google Sign-In and Firebase services work immediately
// when the project is cloned from GitHub, without requiring manual .env creation.
const DEFAULT_FIREBASE_CONFIG = {
  apiKey: 'AIzaSyBg72Hb4w5JKE7Yi5StCvtnQeJceijZ1Ig',
  authDomain: 'astrograph-dc349.firebaseapp.com',
  projectId: 'astrograph-dc349',
  appId: '1:778116751088:web:32cebf97b1ddbcf6e0ec35',
};

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || DEFAULT_FIREBASE_CONFIG.apiKey,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || DEFAULT_FIREBASE_CONFIG.authDomain,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || DEFAULT_FIREBASE_CONFIG.projectId,
  appId: import.meta.env.VITE_FIREBASE_APP_ID || DEFAULT_FIREBASE_CONFIG.appId,
};

export const isFirebaseConfigured = Object.values(config).every(Boolean);

let app = null;
let auth = null;
let db = null;

if (isFirebaseConfigured) {
  try {
    app = getApps().length === 0 ? initializeApp(config) : getApp();
    auth = getAuth(app);
    db = getFirestore(app);
  } catch (err) {
    console.error('Failed to initialize Firebase app:', err);
  }
}

export { app, auth, db };

export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: 'select_account' });
export default app;

