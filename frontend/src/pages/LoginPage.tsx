import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { AppShell } from "../layouts/AppShell";
import { useAuth } from "../utilities/Auth";
import { buttonClassName, cardClassName, textLinkClassName } from "../utilities/classes";
import { usePageTitle } from "../utilities/usePageTitle";

export function LoginPage() {
  usePageTitle("Sign in · LabLink");
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.signIn(email, password);
      navigate(from, { replace: true });
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Sign in">
      <section className={cardClassName}>
        {!auth.configured ? (
          <p className="leading-7 text-muted">
            Firebase Authentication is not configured in this environment. Set the{" "}
            <code>VITE_FIREBASE_*</code> placeholders from <code>frontend/.env.example</code>. There
            is no DEMO identity fallback.
          </p>
        ) : (
          <form
            className="grid gap-4"
            onSubmit={onSubmit}
            {...(error ? { "aria-describedby": "signin-error" } : {})}
          >
            <label className="block text-sm font-medium text-primary">
              Email
              <input
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => {
                  setEmail(event.target.value);
                }}
                required
              />
            </label>
            <label className="block text-sm font-medium text-primary">
              Password
              <input
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
                required
              />
            </label>
            <button className={`${buttonClassName} w-fit`} type="submit" disabled={busy}>
              {busy ? "Signing in" : "Sign in"}
            </button>
          </form>
        )}
        {error ? (
          <p id="signin-error" className="mt-3 text-sm text-ink" role="alert">
            {error}
          </p>
        ) : null}
        <p className="mt-4 text-sm">
          <Link className={textLinkClassName} to="/register">
            Create a student account
          </Link>
        </p>
      </section>
    </AppShell>
  );
}
