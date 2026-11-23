import { useEffect, useState } from "react";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  decideAccessRequest,
  getConflicts,
  listAccessRequests,
  type AccessRequestView,
  type ConflictListResponse,
} from "../utilities/api";
import { buttonClassName, cardClassName } from "../utilities/classes";
import { usePageTitle } from "../utilities/usePageTitle";

export function FacultyReviewPage() {
  usePageTitle("Faculty review · LabLink");
  const [items, setItems] = useState<AccessRequestView[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [comments, setComments] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [conflictEquipment, setConflictEquipment] = useState("eq-oscilloscope");
  const [conflicts, setConflicts] = useState<ConflictListResponse | null>(null);
  const [conflictError, setConflictError] = useState<string | null>(null);

  const faculty = false;

  function load(): void {
    listAccessRequests()
      .then((result) => {
        setItems(result.items);
        setError(null);
        setSelectedId((current) => current ?? result.items.find((item) => item.status === "pending")?.id ?? result.items[0]?.id ?? null);
      })
      .catch((caught: unknown) => {
        setError(caught instanceof ApiError ? caught.message : "Access requests could not be loaded.");
        setItems(null);
      });
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (!faculty) {
      setConflicts(null);
      return;
    }
    getConflicts(conflictEquipment)
      .then((result) => {
        setConflicts(result);
        setConflictError(null);
      })
      .catch((caught: unknown) => {
        setConflictError(caught instanceof ApiError ? caught.message : "Conflicts could not be loaded.");
        setConflicts(null);
      });
  }, [faculty, conflictEquipment]);

  const selected = items?.find((item) => item.id === selectedId) ?? null;
  const pending = items?.filter((item) => item.status === "pending") ?? [];

  async function decide(decision: "approve" | "reject"): Promise<void> {
    if (!selected) {
      return;
    }
    setBusy(true);
    setActionError(null);
    setActionMessage(null);
    try {
      const updated = await decideAccessRequest(selected.id, decision, comments);
      setActionMessage(
        updated.status === "approved" && !updated.booking_id
          ? `Approved ${updated.id}, but no booking was created. Booking checks did not succeed.`
          : `${updated.status} ${updated.id}${updated.booking_id ? ` with booking ${updated.booking_id}` : ""}.`,
      );
      setComments("");
      load();
    } catch (caught: unknown) {
      setActionError(caught instanceof ApiError ? caught.message : "The decision could not be recorded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title="Faculty review">
      <p className="max-w-2xl leading-7 text-muted">
        Approval mutations require a faculty or admin profile from the server. Scores use recorded
        usage and deadlines; missing inputs are marked provisional, not invented.
      </p>

      {!faculty ? (
        <p className="mt-6 rounded-xl bg-aqua px-4 py-3 text-sm text-primary" role="status">
          This account is not faculty or admin. Approve, reject, and conflict rankings stay
          unavailable.
        </p>
      ) : null}

      <section className="mt-8" aria-labelledby="pending-title">
        <h2 id="pending-title" className="font-display text-2xl text-primary">
          Pending requests
        </h2>
        <div className="mt-4">
          {error ? (
            <ErrorState title="Requests unavailable" message={error} />
          ) : items === null ? (
            <LoadingState label="Loading pending requests" />
          ) : pending.length === 0 ? (
            <EmptyState
              title="No pending requests"
              description="Every stored request in this process is already decided, or none exist."
            />
          ) : (
            <ul className="grid list-none gap-2 p-0">
              {pending.map((item) => (
                <li key={item.id}>
                  <button
                    className={`${cardClassName} w-full text-left ${selectedId === item.id ? "border-accent" : ""}`}
                    type="button"
                    onClick={() => {
                      setSelectedId(item.id);
                      setConflictEquipment(item.equipment_id);
                    }}
                  >
                    <span className="font-medium text-primary">{item.id}</span>
                    <span className="mt-1 block text-sm text-muted">
                      {item.equipment_id} · {item.project_id}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {selected ? (
        <section className={`${cardClassName} mt-8`} aria-labelledby="detail-title">
          <h2 id="detail-title" className="font-display text-2xl text-primary">
            Request details
          </h2>
          <dl className="mt-3 grid gap-2 text-sm">
            <div>
              <dt className="font-medium text-primary">Status</dt>
              <dd className="capitalize">{selected.status}</dd>
            </div>
            <div>
              <dt className="font-medium text-primary">Equipment / project</dt>
              <dd>
                {selected.equipment_id} · {selected.project_id}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-primary">Justification</dt>
              <dd>{selected.justification}</dd>
            </div>
            <div>
              <dt className="font-medium text-primary">Slot</dt>
              <dd>
                {selected.start && selected.end
                  ? `${selected.start.replace("T", " ")} – ${selected.end.replace("T", " ")}`
                  : "No slot recorded"}
              </dd>
            </div>
          </dl>
          {faculty && selected.status === "pending" ? (
            <form
              className="mt-4 grid gap-3"
              onSubmit={(event) => {
                event.preventDefault();
              }}
            >
              <label className="block text-sm font-medium text-primary">
                Decision explanation
                <textarea
                  className="mt-1 min-h-24 w-full rounded-xl border border-line px-3 py-2"
                  value={comments}
                  onChange={(event) => {
                    setComments(event.target.value);
                  }}
                  required
                  minLength={4}
                  {...(actionError ? { "aria-describedby": "decision-error" } : {})}
                />
              </label>
              <div className="flex flex-wrap gap-3">
                <button
                  className={buttonClassName}
                  type="button"
                  disabled={busy || comments.trim().length < 4}
                  onClick={() => {
                    void decide("approve");
                  }}
                >
                  Approve
                </button>
                <button
                  className={`${buttonClassName} bg-ink`}
                  type="button"
                  disabled={busy || comments.trim().length < 4}
                  onClick={() => {
                    void decide("reject");
                  }}
                >
                  Reject
                </button>
              </div>
            </form>
          ) : (
            <p className="mt-3 text-sm text-muted">
              {selected.status === "pending"
                ? "Approve and reject stay disabled until a faculty or admin session is active."
                : "This request is already decided. Duplicate decisions are rejected by the API."}
            </p>
          )}
          {actionMessage ? (
            <p className="mt-3 text-sm text-signal" role="status">
              {actionMessage}
            </p>
          ) : null}
          {actionError ? (
            <p id="decision-error" className="mt-3 text-sm text-ink" role="alert">
              {actionError}
            </p>
          ) : null}
        </section>
      ) : null}

      <section className={`${cardClassName} mt-8`} aria-labelledby="conflict-title">
        <h2 id="conflict-title" className="font-display text-2xl text-primary">
          Conflict comparison
        </h2>
        <p className="mt-2 text-sm text-muted">
          Rankings are computed on the server from recorded deadlines, matching scores, department
          approval counts, alternative equipment, and waiting time. Ineligible requests cannot win.
        </p>
        <label className="mt-4 block text-sm font-medium text-primary">
          Equipment ID
          <input
            className="mt-1 min-h-11 w-full max-w-md rounded-xl border border-line px-3"
            value={conflictEquipment}
            onChange={(event) => {
              setConflictEquipment(event.target.value);
            }}
          />
        </label>
        {!faculty ? (
          <p className="mt-3 text-sm text-muted">Conflict scores are faculty-only.</p>
        ) : conflictError ? (
          <p className="mt-3 text-sm text-ink" role="alert">
            {conflictError}
          </p>
        ) : conflicts === null ? (
          <div className="mt-3">
            <LoadingState label="Loading conflict ranking" />
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <p className="text-sm text-muted">{conflicts.note}</p>
            {conflicts.items.length === 0 ? (
              <EmptyState
                title="No competing requests"
                description="This equipment has no pending access requests in this process."
              />
            ) : (
              <table className="mt-3 w-full min-w-[40rem] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-primary">
                    <th className="py-2 pr-3">Rank</th>
                    <th className="py-2 pr-3">Request</th>
                    <th className="py-2 pr-3">Score</th>
                    <th className="py-2 pr-3">Eligible</th>
                    <th className="py-2">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {conflicts.items.map((item) => (
                    <tr key={item.request_id} className="border-b border-line align-top">
                      <td className="py-2 pr-3">{item.rank}</td>
                      <td className="py-2 pr-3">
                        {item.request_id}
                        <span className="mt-1 block text-muted">{item.project_id}</span>
                      </td>
                      <td className="py-2 pr-3">
                        {item.score === null ? "n/a" : item.score.toFixed(3)}
                        {item.provisional ? (
                          <span className="mt-1 block text-muted">provisional</span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-3">
                        {item.eligible ? "yes" : "no"} / {item.feasible ? "feasible" : "blocked"}
                      </td>
                      <td className="py-2">
                        {item.explanation}
                        {item.missing_inputs.length > 0 ? (
                          <span className="mt-1 block text-muted">
                            Missing: {item.missing_inputs.join(", ")}
                          </span>
                        ) : null}
                        {item.alternatives.length > 0 ? (
                          <span className="mt-1 block text-muted">
                            Alternatives: {item.alternatives.join(", ")}
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </section>
    </AppShell>
  );
}
