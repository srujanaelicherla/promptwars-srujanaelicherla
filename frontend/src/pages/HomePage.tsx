import { useEffect, useState } from "react";
import { Link } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { EquipmentCard } from "../components/EquipmentCard";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import { ApiError, listEquipment, type Equipment } from "../utilities/api";
import { buttonClassName, cardClassName, textLinkClassName } from "../utilities/classes";
import { demoDepartments } from "../utilities/demoCatalog";
import { resourceKind } from "../utilities/resourceKind";
import { usePageTitle } from "../utilities/usePageTitle";

export function HomePage() {
  usePageTitle("LabLink");
  const [items, setItems] = useState<Equipment[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listEquipment()
      .then((result) => {
        if (!cancelled) {
          setItems(result.items);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Equipment could not be loaded.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const featured = items
    ? [
        items.find((item) => resourceKind(item) === "equipment"),
        items.find((item) => resourceKind(item) === "lab-station"),
        items.find((item) => resourceKind(item) === "kit"),
      ].filter((item): item is Equipment => Boolean(item))
    : [];

  return (
    <AppShell title="Overview">
      <section className="rounded-2xl bg-primary px-6 py-8 text-on-primary">
        <p className="text-sm font-medium text-mist">DEMO catalog</p>
        <h2 className="mt-2 max-w-2xl font-display text-4xl leading-tight">
          Shared laboratory resources
        </h2>
        <p className="mt-4 max-w-2xl text-base leading-7 text-mist">
          Book equipment, lab stations, and kits in a few steps. Pick an item, choose a free time,
          and confirm. Approval-required items say so before you send a request.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link className={`${buttonClassName} bg-raised text-primary`} to="/equipment">
            Book a resource
          </Link>
          <Link className={`${buttonClassName} bg-ink text-on-primary`} to="/bookings">
            My bookings
          </Link>
        </div>
      </section>

      {items ? (
        <p className="mt-8 text-sm text-muted">{items.length} catalog records from the API</p>
      ) : null}

      <section className="mt-8" aria-labelledby="featured-title">
        <div className="flex items-baseline justify-between gap-4">
          <h2 id="featured-title" className="font-display text-2xl text-primary">
            Featured equipment
          </h2>
          <Link className={textLinkClassName} to="/equipment">
            All equipment
          </Link>
        </div>
        {error ? (
          <div className="mt-4">
            <ErrorState title="Equipment unavailable" message={error} />
          </div>
        ) : items === null ? (
          <div className="mt-4">
            <LoadingState label="Loading equipment" />
          </div>
        ) : featured.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No equipment records" description="The API returned an empty catalog." />
          </div>
        ) : (
          <ul className="mt-4 grid list-none gap-4 p-0 md:grid-cols-3">
            {featured.map((item) => (
              <li key={item.id}>
                <EquipmentCard equipment={item} />
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mt-10" aria-labelledby="departments-title">
        <h2 id="departments-title" className="font-display text-2xl text-primary">
          Departments
        </h2>
        <ul className="mt-4 grid list-none gap-3 p-0 sm:grid-cols-2">
          {demoDepartments.map((department) => (
            <li key={department.id}>
              <Link
                className={`${cardClassName} block hover:border-accent`}
                to={`/equipment?department=${department.id}`}
              >
                <span className="font-medium text-primary">{department.name}</span>
                <span className="mt-1 block text-sm text-muted">Seed ID {department.id}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className={`${cardClassName} mt-10`} aria-labelledby="assistant-title">
        <h2 id="assistant-title" className="font-display text-2xl text-primary">
          LabLink AI Assistant
        </h2>
        <p className="mt-2 leading-7 text-muted">
          Ask about synthetic manuals or extract project requirements. The matcher still ranks
          equipment. The model cannot book or approve.
        </p>
        <Link className={`${buttonClassName} mt-5`} to="/assistant">
          Open AI Assistant
        </Link>
      </section>

      <section className={`${cardClassName} mt-10`} aria-labelledby="matching-title">
        <h2 id="matching-title" className="font-display text-2xl text-primary">
          Project matching
        </h2>
        <p className="mt-2 leading-7 text-muted">
          Rank seed projects against recorded specifications. Scores are not booking feasibility.
        </p>
        <Link className={`${buttonClassName} mt-5`} to="/matching">
          Open project matching
        </Link>
      </section>

      <section className={`${cardClassName} mt-10`} aria-labelledby="approvals-title">
        <h2 id="approvals-title" className="font-display text-2xl text-primary">
          Faculty approvals
        </h2>
        <p className="mt-2 leading-7 text-muted">
          Submit a project access request and inspect its stored status. Restricted items still need
          a faculty decision on the API; this site does not sign in as faculty.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link className={buttonClassName} to="/requests">
            Access requests
          </Link>
        </div>
      </section>
    </AppShell>
  );
}
