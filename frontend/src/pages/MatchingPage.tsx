import { useEffect, useState } from "react";
import { Link } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import { ApiError, getMatches, type EquipmentMatch } from "../utilities/api";
import { cardClassName, textLinkClassName } from "../utilities/classes";
import { demoProjects, departmentName } from "../utilities/demoCatalog";
import { usePageTitle } from "../utilities/usePageTitle";

export function MatchingPage() {
  usePageTitle("Project matching · LabLink");
  const [projectId, setProjectId] = useState<string>(demoProjects[0]?.id ?? "proj-raman");
  const [items, setItems] = useState<EquipmentMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    getMatches(projectId)
      .then((result) => {
        if (!cancelled) {
          setItems(result.items);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Matches could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return (
    <AppShell title="Project matching">
      <p className="max-w-2xl leading-7 text-muted">
        Seed project IDs only. Rankings use recorded specifications, not live availability or
        booking feasibility.
      </p>
      <label className="mt-4 block max-w-md text-sm font-medium text-primary">
        Project
        <select
          className="mt-1 min-h-11 w-full rounded-xl border border-line bg-raised px-3"
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

      <div className="mt-6">
        {error ? (
          <ErrorState title="Matching unavailable" message={error} />
        ) : items === null ? (
          <LoadingState label="Loading matches" />
        ) : items.length === 0 ? (
          <EmptyState title="No matches" description="The API returned no ranked equipment." />
        ) : (
          <ol className="grid list-none gap-4 p-0">
            {items.map((item) => (
              <li key={item.equipment_id} className={cardClassName}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="font-display text-xl text-ink">{item.name}</h2>
                  <p className="text-sm capitalize text-accent">{item.suitability.replaceAll("_", " ")}</p>
                </div>
                <p className="mt-1 text-sm text-muted">
                  {departmentName(item.department_id)} · score {item.score}
                </p>
                <p className="mt-3 text-sm leading-6">{item.explanation}</p>
                <p className="mt-3 text-sm">
                  <span className="font-medium text-primary">Matched:</span>{" "}
                  {item.matched_requirements.join(", ") || "none"}
                </p>
                <p className="mt-1 text-sm">
                  <span className="font-medium text-primary">Unmet:</span>{" "}
                  {item.unmet_requirements.join(", ") || "none"}
                </p>
                <Link className={`${textLinkClassName} mt-3`} to={`/equipment/${item.equipment_id}`}>
                  View equipment
                </Link>
              </li>
            ))}
          </ol>
        )}
      </div>
    </AppShell>
  );
}
