import { useEffect, useState, type FormEvent } from "react";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  createAccessRequest,
  listAccessRequests,
  type AccessRequestView,
} from "../utilities/api";
import { buttonClassName, cardClassName } from "../utilities/classes";
import { useAuth } from "../utilities/Auth";
import { demoProjects } from "../utilities/demoCatalog";
import { usePageTitle } from "../utilities/usePageTitle";

function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

export function AccessRequestsPage() {
  usePageTitle("Access requests · LabLink");
  const { profile } = useAuth();
  const [items, setItems] = useState<AccessRequestView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [apiUser, setApiUser] = useState<string | null>(null);
  const [apiRole, setApiRole] = useState<string | null>(null);
  const [equipmentId, setEquipmentId] = useState("eq-workbench");
  const [projectId, setProjectId] = useState<string>(demoProjects[0]?.id ?? "proj-raman");
  const [justification, setJustification] = useState("");
  const [start, setStart] = useState("2026-12-21T10:00");
  const [end, setEnd] = useState("2026-12-21T12:00");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formMessage, setFormMessage] = useState<string | null>(null);

  function load(): void {
    listAccessRequests()
      .then((result) => {
        setItems(result.items);
        setApiUser(result.demo_user_id);
        setApiRole(result.demo_role);
        setError(null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? caught.message : "Access requests could not be loaded.");
        setItems(null);
      });
  }

  useEffect(() => {
    load();
  }, [profile?.id]);

  async function onSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    setFormMessage(null);
    try {
      const created = await createAccessRequest({
        equipment_id: equipmentId,
        project_id: projectId,
        justification,
        start: localInputToIso(start),
        end: localInputToIso(end),
      });
      setFormMessage(`Request ${created.id} stored as ${created.status}.`);
      setJustification("");
      load();
    } catch (caught: unknown) {
      setFormError(caught instanceof ApiError ? caught.message : "The request could not be submitted.");
    } finally {
      setSubmitting(false);
    }
  }

  const studentView = profile?.role === "student";

  return (
    <AppShell title="Access requests">
      <p className="max-w-2xl leading-7 text-muted">
        Role comes from the server profile
        {apiUser ? ` (${apiUser}` : ""}
        {apiRole ? `, ${apiRole})` : apiUser ? ")" : ""}. The browser cannot send a privileged role.
        Students see their own requests. Faculty see requests in their department. Approval is not a
        booking until booking checks succeed.
      </p>

      {studentView ? (
        <section className={`${cardClassName} mt-8`} aria-labelledby="submit-title">
          <h2 id="submit-title" className="font-display text-2xl text-primary">
            Submit an equipment access request
          </h2>
          <p className="mt-2 text-sm text-muted">
            Restricted equipment still needs faculty approval. Duplicate pending requests for the
            same equipment, project, and slot are rejected.
          </p>
          <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={onSubmit}>
            <label className="block text-sm font-medium text-primary">
              Equipment ID
              <input
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                value={equipmentId}
                onChange={(event) => {
                  setEquipmentId(event.target.value);
                }}
                required
              />
            </label>
            <label className="block text-sm font-medium text-primary">
              Project
              <select
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                value={projectId}
                onChange={(event) => {
                  setProjectId(event.target.value);
                }}
              >
                {demoProjects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="block text-sm font-medium text-primary">
              Start
              <input
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                type="datetime-local"
                value={start}
                onChange={(event) => {
                  setStart(event.target.value);
                }}
                required
              />
            </label>
            <label className="block text-sm font-medium text-primary">
              End
              <input
                className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
                type="datetime-local"
                value={end}
                onChange={(event) => {
                  setEnd(event.target.value);
                }}
                required
              />
            </label>
            <label className="sm:col-span-2 block text-sm font-medium text-primary">
              Justification
              <textarea
                className="mt-1 min-h-24 w-full rounded-xl border border-line px-3 py-2"
                value={justification}
                onChange={(event) => {
                  setJustification(event.target.value);
                }}
                required
                minLength={8}
              />
            </label>
            <button className={`${buttonClassName} sm:w-fit`} type="submit" disabled={submitting}>
              {submitting ? "Submitting" : "Submit request"}
            </button>
          </form>
          {formMessage ? (
            <p className="mt-3 text-sm text-signal" role="status">
              {formMessage}
            </p>
          ) : null}
          {formError ? (
            <p className="mt-3 text-sm text-ink" role="alert">
              {formError}
            </p>
          ) : null}
        </section>
      ) : (
        <p className="mt-6 rounded-xl bg-aqua px-4 py-3 text-sm text-primary">
          Student accounts submit requests here. Faculty review is on Faculty Review.
        </p>
      )}

      <section className="mt-8" aria-labelledby="list-title">
        <h2 id="list-title" className="font-display text-2xl text-primary">
          Request status
        </h2>
        <div className="mt-4">
          {error ? (
            <ErrorState title="Requests unavailable" message={error} />
          ) : items === null ? (
            <LoadingState label="Loading access requests" />
          ) : items.length === 0 ? (
            <EmptyState
              title="No access requests"
              description="This account has no stored requests in this API process."
            />
          ) : (
            <ul className="grid list-none gap-3 p-0">
              {items.map((item) => (
                <li key={item.id} className={cardClassName}>
                  <p className="font-medium text-primary">{item.id}</p>
                  <p className="mt-1 text-sm text-muted">
                    {item.equipment_id} · {item.project_id} · {item.status}
                  </p>
                  <p className="mt-2 text-sm">{item.justification}</p>
                  {item.start && item.end ? (
                    <p className="mt-2 text-sm">
                      {item.start.replace("T", " ")} – {item.end.replace("T", " ")}
                    </p>
                  ) : (
                    <p className="mt-2 text-sm text-muted">No requested slot on this record.</p>
                  )}
                  {item.approvals.length === 0 ? (
                    <p className="mt-2 text-sm text-muted">No faculty decision yet.</p>
                  ) : (
                    <ul className="mt-2 space-y-1 text-sm">
                      {item.approvals.map((approval) => (
                        <li key={approval.id}>
                          {approval.decision} at {approval.decided_at.replace("T", " ")}:{" "}
                          {approval.comments || "No explanation recorded."}
                          {item.booking_id ? ` Booking ${item.booking_id}.` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </AppShell>
  );
}
