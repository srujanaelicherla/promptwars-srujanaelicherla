import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";
import { AppShell } from "../layouts/AppShell";
import { useAuth } from "../utilities/Auth";
import { buttonClassName, cardClassName, textLinkClassName } from "../utilities/classes";
import { demoDepartments } from "../utilities/demoCatalog";
import { usePageTitle } from "../utilities/usePageTitle";

export function RegisterPage() {
  usePageTitle("Register · LabLink");
  const auth = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [departmentId, setDepartmentId] = useState<string>(demoDepartments[0]?.id ?? "dept-physics");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.register(email, password, departmentId);
      navigate("/", { replace: true });
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Registration failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Create account">
      <section className={cardClassName}>
        <p className="leading-7 text-muted">
          New accounts are students only. Faculty and admin roles are assigned by a trusted backend
          process, not this form.
        </p>
        {!auth.configured ? (
          <p className="mt-4 leading-7 text-muted">
            Firebase Authentication is not configured. Registration is disabled.
          </p>
        ) : (
          <form
            className="mt-4 grid gap-4"
            onSubmit={onSubmit}
            {...(error ? { "aria-describedby": "register-error" } : {})}
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
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                }}
                required
              />
            </label>
            <label className="block text-sm font-medium text-primary">
              Department
              <select
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                value={departmentId}
                onChange={(event) => {
                  setDepartmentId(event.target.value);
                }}
              >
                {demoDepartments.map((department) => (
                  <option key={department.id} value={department.id}>
                    {department.name}
                  </option>
                ))}
              </select>
            </label>
            <button className={`${buttonClassName} w-fit`} type="submit" disabled={busy}>
              {busy ? "Creating account" : "Register as student"}
            </button>
          </form>
        )}
        {error ? (
          <p id="register-error" className="mt-3 text-sm text-ink" role="alert">
            {error}
          </p>
        ) : null}
        <p className="mt-4 text-sm">
          <Link className={textLinkClassName} to="/login">
            Already have an account
          </Link>
        </p>
      </section>
    </AppShell>
  );
}
