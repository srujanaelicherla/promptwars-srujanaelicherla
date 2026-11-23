import { Link } from "react-router";
import type { ReactNode } from "react";
import { AppNav } from "../components/AppNav";
import { CompleteStudentProfile } from "../components/CompleteStudentProfile";
import { useAuth } from "../utilities/Auth";
import { secondaryButtonClassName } from "../utilities/classes";

type AppShellProps = {
  title: string;
  children: ReactNode;
};

export function AppShell({ title, children }: AppShellProps) {
  const auth = useAuth();

  return (
    <div className="min-h-screen bg-paper text-ink md:grid md:grid-cols-[17rem_1fr]">
      <AppNav />
      <div className="flex min-w-0 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-raised px-5 py-4 sm:px-8">
          <h1 className="font-display text-2xl text-primary">{title}</h1>
          <div className="flex flex-wrap items-center gap-3">
            {auth.firebaseUser ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-muted">
                  {auth.firebaseUser.email ?? "Signed in"}
                  {auth.profile ? ` · ${auth.profile.role}` : " · signed in"}
                </p>
                <button
                  className={secondaryButtonClassName}
                  type="button"
                  onClick={() => {
                    void auth.signOut();
                  }}
                >
                  Sign out
                </button>
              </div>
            ) : (
              <Link className={secondaryButtonClassName} to="/login">
                Sign in
              </Link>
            )}
            <p className="rounded-full bg-mist px-3 py-1 text-sm font-medium text-signal">
              Synthetic catalog
            </p>
          </div>
        </header>
        {auth.expired && !auth.needsProfile ? (
          <p className="bg-aqua px-5 py-3 text-sm text-primary sm:px-8" role="alert">
            Your session expired. Sign in again to continue.
          </p>
        ) : null}
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-5 py-8 sm:px-8">
          {auth.needsProfile ? <CompleteStudentProfile /> : null}
          {children}
        </main>
        <footer className="border-t border-line px-5 py-4 text-sm text-muted sm:px-8">
          Catalog records are synthetic. Bookings persist in Firestore when configured; they are not
          live laboratory records.
        </footer>
      </div>
    </div>
  );
}
