import { initializeApp, type FirebaseApp, type FirebaseOptions } from "@firebase/app";
import {
  browserLocalPersistence,
  connectAuthEmulator,
  getAuth,
  setPersistence,
  type Auth,
} from "@firebase/auth";

export function firebaseConfigured(): boolean {
  return Boolean(import.meta.env.VITE_FIREBASE_API_KEY && import.meta.env.VITE_FIREBASE_PROJECT_ID);
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

export function getFirebaseAuth(): Auth | null {
  if (!firebaseConfigured()) {
    return null;
  }
  if (auth) {
    return auth;
  }
  const options: FirebaseOptions = {
    apiKey: import.meta.env.VITE_FIREBASE_API_KEY ?? "",
    projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID ?? "",
  };
  if (import.meta.env.VITE_FIREBASE_AUTH_DOMAIN) {
    options.authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN;
  }
  if (import.meta.env.VITE_FIREBASE_APP_ID) {
    options.appId = import.meta.env.VITE_FIREBASE_APP_ID;
  }
  app = initializeApp(options);
  auth = getAuth(app);
  void setPersistence(auth, browserLocalPersistence);
  const emulator = import.meta.env.VITE_FIREBASE_AUTH_EMULATOR_URL;
  if (emulator) {
    connectAuthEmulator(auth, emulator, { disableWarnings: true });
  }
  return auth;
}
