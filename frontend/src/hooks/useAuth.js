import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react';
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendPasswordResetEmail,
  sendEmailVerification,
  signOut,
} from 'firebase/auth';
import { auth, googleProvider, isFirebaseConfigured } from '../firebase.js';

const MESSAGES = {
  'auth/invalid-email': 'That email address looks invalid.',
  'auth/missing-password': 'Enter your password.',
  'auth/weak-password': 'Password must be at least 6 characters.',
  'auth/email-already-in-use': 'An account with this email already exists. Try signing in.',
  'auth/invalid-credential': 'Wrong email or password.',
  'auth/user-not-found': 'No account found for this email.',
  'auth/wrong-password': 'Wrong email or password.',
  'auth/too-many-requests': 'Too many attempts. Please wait a bit and try again.',
  'auth/network-request-failed': 'Network error. Check your connection.',
  'auth/popup-closed-by-user': 'Google sign-in was closed before finishing.',
  'auth/cancelled-popup-request': 'Google sign-in was cancelled.',
  'auth/unauthorized-domain':
    'This domain is not authorised in Firebase. If running locally, please open http://localhost:5173 or add this domain under Firebase Console → Authentication → Settings → Authorized domains.',
  'auth/operation-not-allowed':
    'This sign-in method is not enabled in the Firebase console yet.',
};

export function friendlyError(err) {
  return MESSAGES[err?.code] || err?.message || 'Something went wrong. Please try again.';
}

const AuthContext = createContext(null);

function useAuthState() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // 1. Check for saved guest session
    try {
      const savedGuest = localStorage.getItem('astrograph_guest_user');
      if (savedGuest) {
        const parsed = JSON.parse(savedGuest);
        if (parsed?.uid) {
          parsed.getIdToken = async () => 'mock-guest-token';
          setUser(parsed);
          setReady(true);
        }
      }
    } catch {
      localStorage.removeItem('astrograph_guest_user');
    }

    // 2. If Firebase auth is not available, mark ready and return
    if (!auth) {
      setReady(true);
      return undefined;
    }

    // 3. Listen for Firebase Auth changes
    getRedirectResult(auth).catch(() => {});
    const unsubscribe = onAuthStateChanged(auth, (u) => {
      if (u) {
        try {
          localStorage.removeItem('astrograph_guest_user');
        } catch {}
        setUser(u);
      } else {
        // If there's an active guest session, keep it; otherwise clear user
        const guestActive = localStorage.getItem('astrograph_guest_user');
        if (!guestActive) {
          setUser(null);
        }
      }
      setReady(true);
    });

    return unsubscribe;
  }, []);

  const google = useCallback(async () => {
    if (!auth) {
      throw new Error('Google Sign-In is not initialized. Please verify Firebase configuration.');
    }
    try {
      try {
        localStorage.removeItem('astrograph_guest_user');
      } catch {}
      const result = await signInWithPopup(auth, googleProvider);
      if (result?.user) {
        setUser(result.user);
      }
      return result?.user;
    } catch (err) {
      if (err?.code === 'auth/popup-blocked') {
        await signInWithRedirect(auth, googleProvider);
        return null;
      }
      throw err;
    }
  }, []);

  const guestSignIn = useCallback(async () => {
    const guestUser = {
      uid: 'guest_' + Math.random().toString(36).substring(2, 9),
      email: 'guest@astrograph.local',
      displayName: 'Guest Explorer',
      isGuest: true,
      getIdToken: async () => 'mock-guest-token',
    };
    try {
      localStorage.setItem('astrograph_guest_user', JSON.stringify(guestUser));
    } catch {}
    setUser(guestUser);
    setReady(true);
    return guestUser;
  }, []);

  const signUp = useCallback(async (email, password) => {
    if (!auth) throw new Error('Authentication service is not initialized.');
    try {
      localStorage.removeItem('astrograph_guest_user');
    } catch {}
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    sendEmailVerification(cred.user).catch(() => {});
  }, []);

  const signIn = useCallback(async (email, password) => {
    if (!auth) throw new Error('Authentication service is not initialized.');
    try {
      localStorage.removeItem('astrograph_guest_user');
    } catch {}
    return signInWithEmailAndPassword(auth, email, password);
  }, []);

  const reset = useCallback((email) => {
    if (!auth) throw new Error('Authentication service is not initialized.');
    return sendPasswordResetEmail(auth, email);
  }, []);

  const logout = useCallback(async () => {
    try {
      localStorage.removeItem('astrograph_guest_user');
      if (auth) {
        await signOut(auth);
      }
    } finally {
      setUser(null);
    }
  }, []);

  // Fresh Firebase ID token, sent to the backend so it can tell who the user is.
  const getToken = useCallback(async () => {
    if (user?.isGuest) return 'mock-guest-token';
    return auth?.currentUser ? auth.currentUser.getIdToken() : null;
  }, [user]);

  return { user, ready, google, guestSignIn, signUp, signIn, reset, logout, getToken };
}

// One shared auth state for the whole app (wrap <App /> content with this).
export function AuthProvider({ children }) {
  const value = useAuthState();
  return createElement(AuthContext.Provider, { value }, children);
}

export default function useAuth() {
  return useContext(AuthContext);
}
