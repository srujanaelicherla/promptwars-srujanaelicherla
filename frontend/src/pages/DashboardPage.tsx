import { useEffect, useId, useState } from "react";
import { Link } from "react-router";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { AppShell } from "../layouts/AppShell";
import {
  ApiError,
  getAnalyticsDepartments,
  getAnalyticsEquipment,
  getAnalyticsOverview,
  type AnalyticsOverview,
  type DepartmentAnalytics,
  type EquipmentAnalytics,
} from "../utilities/api";
import { cardClassName, textLinkClassName } from "../utilities/classes";
import { departmentName } from "../utilities/demoCatalog";
import { usePageTitle } from "../utilities/usePageTitle";

function dayStart(value: string): string {
  return `${value}T00:00:00.000Z`;
}

function dayEnd(value: string): string {
  return `${value}T23:59:59.000Z`;
}

function OccupiedBars({ items }: { items: DepartmentAnalytics[] }) {
  const max = Math.max(...items.map((item) => item.occupied_minutes), 0);
  if (max === 0) {
    return (
      <EmptyState
        title="No occupied time"
        description="Confirmed bookings in this window produced no occupied resource-time."
      />
    );
  }
  return (
    <svg viewBox={`0 0 400 ${items.length * 36 + 8}`} role="img" aria-label="Occupied minutes by department">
      {items.map((item, index) => {
        const width = Math.max(4, (item.occupied_minutes / max) * 240);
        const y = index * 36 + 8;
        return (
          <g key={item.department_id}>
            <text x="0" y={y + 14} fill="#0c3c39" fontSize="12">
              {departmentName(item.department_id)}
            </text>
            <rect x="150" y={y} width={width} height="20" fill="#1a7a72" />
            <text x={158 + width} y={y + 14} fill="#17211f" fontSize="12">
              {item.occupied_minutes} min
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function DashboardPage() {
  usePageTitle("Dashboard · LabLink");
  const startId = useId();
  const endId = useId();
  const [startDate, setStartDate] = useState("2026-12-01");
  const [endDate, setEndDate] = useState("2026-12-31");
  const [overview, setOverview] = useState<AnalyticsOverview | null>(null);
  const [departments, setDepartments] = useState<DepartmentAnalytics[] | null>(null);
  const [equipment, setEquipment] = useState<EquipmentAnalytics[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const start = dayStart(startDate);
    const end = dayEnd(endDate);
    Promise.all([getAnalyticsOverview(start, end), getAnalyticsDepartments(start, end), getAnalyticsEquipment(start, end)])
      .then(([nextOverview, nextDepartments, nextEquipment]) => {
        if (cancelled) {
          return;
        }
        setOverview(nextOverview);
        setDepartments(nextDepartments.items);
        setEquipment(nextEquipment.items);
      })
      .catch((caught: unknown) => {
        if (cancelled) {
          return;
        }
        setOverview(null);
        setDepartments(null);
        setEquipment(null);
        setError(caught instanceof ApiError ? caught.message : "Analytics could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [startDate, endDate]);

  const counts = overview?.counts;
  const underused = equipment?.filter((item) => item.underused) ?? [];

  return (
    <AppShell title="Dashboard">
      <p className="max-w-2xl leading-7 text-muted">
        Figures come from stored bookings, catalog equipment, access requests, and waitlist rows.
        Utilization percent is omitted when operating hours are not configured. All records are
        synthetic.
      </p>

      <form
        className={`${cardClassName} mt-6 grid gap-3 sm:grid-cols-2`}
        aria-labelledby="range-title"
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <h2 id="range-title" className="font-display text-xl text-primary sm:col-span-2">
          Date range
        </h2>
        <label className="text-sm font-medium text-primary" htmlFor={startId}>
          Start
          <input
            id={startId}
            className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
            type="date"
            value={startDate}
            onChange={(event) => {
              setStartDate(event.target.value);
            }}
          />
        </label>
        <label className="text-sm font-medium text-primary" htmlFor={endId}>
          End
          <input
            id={endId}
            className="mt-1 min-h-11 w-full rounded-xl border border-line px-3"
            type="date"
            value={endDate}
            onChange={(event) => {
              setEndDate(event.target.value);
            }}
          />
        </label>
      </form>

      <div className="mt-6" aria-live="polite">
        {loading ? <LoadingState label="Loading analytics" /> : null}
        {error ? <ErrorState title="Analytics unavailable" message={error} /> : null}
      </div>

      {!loading && !error && overview && counts ? (
        <>
          <section className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" aria-labelledby="summary-title">
            <h2 id="summary-title" className="sr-only">
              Summary
            </h2>
            {[
              ["Active equipment", counts.equipment_active],
              ["Confirmed bookings", counts.confirmed_bookings],
              ["Pending requests", counts.pending_requests],
              ["Waitlist waiting", counts.waitlist_waiting],
            ].map(([label, value]) => (
              <article key={label} className={cardClassName}>
                <h3 className="text-sm font-medium text-muted">{label}</h3>
                <p className="mt-2 font-display text-3xl text-primary">{value}</p>
              </article>
            ))}
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="util-title">
            <h2 id="util-title" className="font-display text-xl text-primary">
              Utilization
            </h2>
            {overview.utilization.percent === null ? (
              <p className="mt-3 leading-7 text-muted" role="status">
                {overview.utilization.unavailable_reason} Occupied resource-time in this window is{" "}
                {overview.utilization.occupied_minutes} minutes. Capacity is{" "}
                {overview.utilization.capacity_per_slot} booking per slot.
              </p>
            ) : (
              <p className="mt-3 font-display text-4xl text-primary">{overview.utilization.percent}%</p>
            )}
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="dept-title">
            <h2 id="dept-title" className="font-display text-xl text-primary">
              Department occupied time
            </h2>
            <div className="mt-4">
              {departments && departments.length > 0 ? (
                <OccupiedBars items={departments} />
              ) : (
                <EmptyState title="No departments" description="The API returned no department rows." />
              )}
            </div>
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="booked-title">
            <h2 id="booked-title" className="font-display text-xl text-primary">
              Most booked equipment
            </h2>
            {overview.most_booked.filter((item) => item.occupied_minutes > 0).length === 0 ? (
              <div className="mt-4">
                <EmptyState
                  title="No confirmed occupancy"
                  description="No confirmed bookings overlap this window."
                />
              </div>
            ) : (
              <table className="mt-4 w-full text-left text-sm">
                <caption className="sr-only">Equipment ranked by occupied minutes</caption>
                <thead>
                  <tr className="border-b border-line text-muted">
                    <th className="py-2 font-medium" scope="col">
                      Equipment
                    </th>
                    <th className="py-2 font-medium" scope="col">
                      Occupied minutes
                    </th>
                    <th className="py-2 font-medium" scope="col">
                      Confirmed bookings
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {overview.most_booked
                    .filter((item) => item.occupied_minutes > 0)
                    .map((item) => (
                      <tr key={item.equipment_id} className="border-b border-line">
                        <td className="py-2">
                          <Link className={textLinkClassName} to={`/equipment/${item.equipment_id}`}>
                            {item.name}
                          </Link>
                        </td>
                        <td className="py-2">{item.occupied_minutes}</td>
                        <td className="py-2">{item.confirmed_bookings}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="demand-title">
            <h2 id="demand-title" className="font-display text-xl text-primary">
              Demand by category
            </h2>
            {overview.demand_by_category.length === 0 ? (
              <EmptyState title="No demand rows" description="No category demand was recorded." />
            ) : (
              <ul className="mt-3 grid list-none gap-2 p-0">
                {overview.demand_by_category.map((item) => (
                  <li key={item.category} className="flex justify-between gap-4 text-sm">
                    <span className="capitalize">{item.category}</span>
                    <span className="text-muted">
                      {item.pending_requests} pending · {item.waitlist_waiting} waitlist ·{" "}
                      {item.confirmed_bookings} confirmed
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="wait-title">
            <h2 id="wait-title" className="font-display text-xl text-primary">
              Waitlist
            </h2>
            {overview.waitlist_demand.length === 0 ? (
              <div className="mt-4">
                <EmptyState title="No waitlist demand" description="No waiting entries are stored for this scope." />
              </div>
            ) : (
              <ul className="mt-3 grid list-none gap-2 p-0 text-sm">
                {overview.waitlist_demand.map((item) => (
                  <li key={item.equipment_id}>
                    {item.name}: {item.waitlist_waiting} waiting
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="pending-title">
            <h2 id="pending-title" className="font-display text-xl text-primary">
              Pending approvals
            </h2>
            <p className="mt-2 text-sm text-muted">{counts.pending_requests} pending access requests in scope.</p>
            <p className="mt-2 text-sm text-muted">{counts.conflicts} equipment rows have overlapping pending requests.</p>
            {overview.approval_turnaround.sample_size > 0 ? (
              <p className="mt-2 text-sm">
                Median approval turnaround {overview.approval_turnaround.median_hours} hours (
                {overview.approval_turnaround.sample_size} timestamps).
              </p>
            ) : (
              <p className="mt-2 text-sm text-muted">
                {overview.approval_turnaround.unavailable_reason ?? "No approval timestamps are available."}
              </p>
            )}
            <p className="mt-3">
              <Link className={textLinkClassName} to="/faculty">
                Open faculty review
              </Link>
            </p>
          </section>

          <section className={`${cardClassName} mt-8`} aria-labelledby="underused-title">
            <h2 id="underused-title" className="font-display text-xl text-primary">
              Underused equipment
            </h2>
            {underused.length === 0 ? (
              <p className="mt-2 text-sm text-muted">Every active item has occupied time in this window, or none are active.</p>
            ) : (
              <ul className="mt-3 grid list-none gap-2 p-0 text-sm">
                {underused.map((item) => (
                  <li key={item.equipment_id}>
                    <Link className={textLinkClassName} to={`/equipment/${item.equipment_id}`}>
                      {item.name}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
