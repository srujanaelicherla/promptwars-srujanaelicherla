import {
  createUserWithEmailAndPassword,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  type User,
} from "@firebase/auth";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  bootstrapProfile,
  getMe,
  isCredentialFailure,
  isMissingProfileError,
  setTokenProvider,
  setUnauthorizedHandler,
  type MeResponse,
} from "./api";
import { firebaseConfigured, getFirebaseAuth } from "./firebase";

export type AuthValue = {
  ready: boolean;
  configured: boolean;
  firebaseUser: User | null;
  profile: MeResponse | null;
  needsProfile: boolean;
  error: string | null;
  expired: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, departmentId: string) => Promise<void>;
  completeStudentProfile: (departmentId: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const configured = firebaseConfigured();
  const [ready, setReady] = useState(!configured);
  const [firebaseUser, setFirebaseUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    setTokenProvider(async () => {
      const auth = getFirebaseAuth();
      const current = auth?.currentUser;
      if (!current) {
        return null;
      }
      return current.getIdToken();
    });
    setUnauthorizedHandler(() => {
      setExpired(true);
      setProfile(null);
      const auth = getFirebaseAuth();
      if (auth?.currentUser) {
        void firebaseSignOut(auth);
      }
    });
  }, []);

  useEffect(() => {
    const auth = getFirebaseAuth();
    if (!auth) {
      setReady(true);
      return;
    }
    return onAuthStateChanged(auth, (user) => {
      setFirebaseUser(user);
      if (!user) {
        setProfile(null);
        setNeedsProfile(false);
        setReady(true);
        return;
      }
      getMe()
        .then((me) => {
          setProfile(me);
          setNeedsProfile(false);
          setExpired(false);
          setError(null);
        })
        .catch((caught: unknown) => {
          setProfile(null);
          if (isMissingProfileError(caught)) {
            setNeedsProfile(true);
            setExpired(false);
            setError(null);
            return;
          }
          setNeedsProfile(false);
          if (isCredentialFailure(caught)) {
            return;
          }
          setError(caught instanceof Error ? caught.message : "Profile could not be loaded.");
        })
        .finally(() => {
          setReady(true);
        });
    });
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      ready,
      configured,
      firebaseUser,
      profile,
      needsProfile,
      error,
      expired,
      signIn: async (email, password) => {
        const auth = getFirebaseAuth();
        if (!auth) {
          throw new Error("Firebase Authentication is not configured.");
        }
        setError(null);
        await signInWithEmailAndPassword(auth, email, password);
      },
      register: async (email, password, departmentId) => {
        const auth = getFirebaseAuth();
        if (!auth) {
          throw new Error("Firebase Authentication is not configured.");
        }
        setError(null);
        const credential = await createUserWithEmailAndPassword(auth, email, password);
        await credential.user.getIdToken();
        const me = await bootstrapProfile(departmentId);
        setProfile(me);
        setNeedsProfile(false);
      },
      completeStudentProfile: async (departmentId) => {
        try {
          const me = await bootstrapProfile(departmentId);
          setProfile(me);
        } catch (caught: unknown) {
          if (!(caught instanceof ApiError) || caught.status !== 409) {
            throw caught;
          }
          setProfile(await getMe());
        }
        setNeedsProfile(false);
        setExpired(false);
        setError(null);
      },
      signOut: async () => {
        const auth = getFirebaseAuth();
        if (auth) {
          await firebaseSignOut(auth);
        }
        setProfile(null);
        setNeedsProfile(false);
        setExpired(false);
      },
    }),
    [configured, error, expired, firebaseUser, needsProfile, profile, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("AuthProvider is missing.");
  }
  return value;
}
