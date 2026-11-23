import type { ReactNode } from "react";
import { AppNav } from "../components/AppNav";

type AppShellProps = {
  title: string;
  children: ReactNode;
};

export function AppShell({ title, children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-paper text-ink md:grid md:grid-cols-[17rem_1fr]">
      <AppNav />
      <div className="flex min-w-0 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-raised px-5 py-4 sm:px-8">
          <h1 className="font-display text-2xl text-primary">{title}</h1>
          <p className="rounded-full bg-mist px-3 py-1 text-sm font-medium text-signal">
            Synthetic catalog
          </p>
        </header>
        <main id="main" tabIndex={-1} className="mx-auto w-full max-w-5xl flex-1 px-5 py-8 sm:px-8">
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
