import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";
import { DashboardPage } from "./DashboardPage";

const overview = {
  start: "2026-12-01T00:00:00Z",
  end: "2026-12-31T23:59:59Z",
  counts: {
    equipment_total: 9,
    equipment_active: 8,
    confirmed_bookings: 1,
    pending_requests: 1,
    waitlist_waiting: 0,
    waitlist_offered: 0,
    conflicts: 0,
  },
  utilization: {
    percent: null,
    occupied_minutes: 120,
    available_minutes: null,
    unavailable_reason: "Operating hours are not configured; eligible available resource-time cannot be computed.",
    capacity_per_slot: 1,
  },
  most_booked: [
    {
      equipment_id: "eq-oscilloscope",
      name: "Digital oscilloscope",
      department_id: "dept-engineering",
      category: "electronics",
      occupied_minutes: 120,
      confirmed_bookings: 1,
      pending_requests: 0,
      waitlist_waiting: 0,
      underused: false,
      utilization: {
        percent: null,
        occupied_minutes: 120,
        available_minutes: null,
        unavailable_reason: "Operating hours are not configured.",
        capacity_per_slot: 1,
      },
    },
  ],
  demand_by_category: [
    { category: "electronics", pending_requests: 0, waitlist_waiting: 0, confirmed_bookings: 1 },
  ],
  waitlist_demand: [],
  approval_turnaround: { sample_size: 1, median_hours: 53, unavailable_reason: null },
  source: "synthetic",
  demo: true,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

test("dashboard renders API summary, unavailable utilization, and refetches on date change", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/analytics/overview")) {
      return json(overview);
    }
    if (url.includes("/analytics/departments")) {
      return json({
        start: overview.start,
        end: overview.end,
        items: [
          {
            department_id: "dept-engineering",
            occupied_minutes: 120,
            confirmed_bookings: 1,
            pending_requests: 0,
            waitlist_waiting: 0,
            utilization: overview.utilization,
          },
        ],
        source: "synthetic",
        demo: true,
      });
    }
    return json({ start: overview.start, end: overview.end, items: overview.most_booked, source: "synthetic", demo: true });
  });
  globalThis.fetch = fetchMock as typeof fetch;

  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("status", { name: "Loading analytics" })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Confirmed bookings" })).toBeInTheDocument();
  expect(screen.getByText(/eligible available resource-time/i)).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Occupied minutes" })).toBeInTheDocument();
  expect(screen.getByLabelText("Start")).toHaveValue("2026-12-01");

  fireEvent.change(screen.getByLabelText("Start"), { target: { value: "2026-11-01" } });
  await waitFor(() => {
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("2026-11-01"))).toBe(true);
  });
});

test("dashboard shows API error", async () => {
  globalThis.fetch = vi.fn(async () => json({ error: "unavailable", message: "Analytics could not be loaded." }, 503)) as typeof fetch;

  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: "Analytics unavailable" })).toBeInTheDocument();
});

test("dashboard empty occupancy and labeled date fields", async () => {
  const empty = {
    ...overview,
    counts: {
      equipment_total: 9,
      equipment_active: 8,
      confirmed_bookings: 0,
      pending_requests: 0,
      waitlist_waiting: 0,
      waitlist_offered: 0,
      conflicts: 0,
    },
    utilization: {
      ...overview.utilization,
      occupied_minutes: 0,
    },
    most_booked: [],
    demand_by_category: [],
    waitlist_demand: [],
    approval_turnaround: { sample_size: 0, median_hours: null, unavailable_reason: "No approval timestamps are available." },
  };
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/analytics/overview")) {
      return json(empty);
    }
    if (url.includes("/analytics/departments")) {
      return json({
        start: empty.start,
        end: empty.end,
        items: [
          {
            department_id: "dept-engineering",
            occupied_minutes: 0,
            confirmed_bookings: 0,
            pending_requests: 0,
            waitlist_waiting: 0,
            utilization: empty.utilization,
          },
        ],
        source: "synthetic",
        demo: true,
      });
    }
    return json({ start: empty.start, end: empty.end, items: [], source: "synthetic", demo: true });
  }) as typeof fetch;

  render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: "No occupied time" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "No confirmed occupancy" })).toBeInTheDocument();
  expect(screen.getByLabelText("Start")).toHaveAttribute("type", "date");
  expect(screen.getByLabelText("End")).toHaveAttribute("type", "date");
  fireEvent.keyDown(screen.getByLabelText("Start"), { key: "Tab" });
  expect(screen.getByLabelText("Start")).toBeEnabled();
});
