import { afterEach, expect, test, vi } from "vitest";
import { ApiError, createBooking, setTokenProvider } from "./api";

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  setTokenProvider(async () => null);
});

const slot = {
  equipment_id: "eq-workbench",
  project_id: "proj-sensor",
  start: "2026-12-20T10:00:00.000Z",
  end: "2026-12-20T12:00:00.000Z",
};

test("booking conflict keeps the API message instead of a reachability error", async () => {
  setTokenProvider(async () => "aaa.bbb.ccc");
  globalThis.fetch = vi.fn(async () =>
    json({ error: "conflict", message: "This slot overlaps an existing booking." }, 409),
  ) as typeof fetch;

  await expect(createBooking(slot)).rejects.toEqual(
    expect.objectContaining({
      status: 409,
      code: "conflict",
      message: "This slot overlaps an existing booking.",
    }),
  );
});

test("restricted and maintenance errors keep their API messages", async () => {
  setTokenProvider(async () => "aaa.bbb.ccc");
  globalThis.fetch = vi.fn(async () =>
    json({ error: "unavailable", message: "This equipment is not operational." }, 409),
  ) as typeof fetch;

  await expect(createBooking({ ...slot, equipment_id: "eq-fume-hood" })).rejects.toBeInstanceOf(ApiError);
  await expect(createBooking({ ...slot, equipment_id: "eq-fume-hood" })).rejects.toMatchObject({
    message: "This equipment is not operational.",
  });
});

test("a dropped connection is the only reachability error", async () => {
  setTokenProvider(async () => "aaa.bbb.ccc");
  globalThis.fetch = vi.fn(async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;

  await expect(createBooking(slot)).rejects.toMatchObject({
    status: 0,
    message: "The LabLink API could not be reached.",
  });
});
