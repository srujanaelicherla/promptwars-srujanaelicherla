import { useState, type FormEvent } from "react";
import { useAuth } from "../utilities/Auth";
import { buttonClassName, cardClassName } from "../utilities/classes";
import { demoDepartments } from "../utilities/demoCatalog";

export function CompleteStudentProfile() {
  const auth = useAuth();
  const [departmentId, setDepartmentId] = useState<string>(demoDepartments[0]?.id ?? "dept-physics");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await auth.completeStudentProfile(departmentId);
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "The student profile could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`${cardClassName} mb-8`} aria-labelledby="complete-profile-title">
      <h2 id="complete-profile-title" className="font-display text-2xl text-primary">
        Finish student profile
      </h2>
      <p className="mt-2 leading-7 text-muted">
        You are signed in
        {auth.firebaseUser?.email ? ` as ${auth.firebaseUser.email}` : ""}. This creates a student
        profile for your current Firebase account. Faculty and admin roles cannot be chosen here.
      </p>
      <form
        className="mt-4 grid gap-4"
        onSubmit={onSubmit}
        {...(error ? { "aria-describedby": "complete-profile-error" } : {})}
      >
        <label className="block text-sm font-medium text-primary">
          Department
          <select
            className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
            name="department_id"
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
          {busy ? "Saving profile" : "Create student profile"}
        </button>
      </form>
      {error ? (
        <p id="complete-profile-error" className="mt-3 text-sm text-ink" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
