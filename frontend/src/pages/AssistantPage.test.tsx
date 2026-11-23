import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantPage } from "./AssistantPage";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

test("assistant page is visible with examples and a send form", () => {
  render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { level: 1, name: "LabLink AI Assistant" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Example questions" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /SYNTHETIC booking duration/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Send question" })).toBeDisabled();
  expect(screen.queryByRole("heading", { name: "Sign in required" })).not.toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByText("Project description")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Extract requirements" })).not.toBeInTheDocument();
});

test("sending a question renders a cited answer", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/ai/assistant/query")) {
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body ?? "{}"))).toEqual({
        question: "What is the SYNTHETIC booking duration limit?",
      });
      expect(String(init?.headers ?? "")).not.toMatch(/Authorization/i);
      return json({
        answer: "Bookings last at most four hours in the SYNTHETIC notes.",
        citations: [
          {
            title: "synthetic booking guidelines",
            section: "Duration",
            doc_id: "booking-guidelines",
            synthetic: true,
          },
        ],
        equipment_ids: [],
        evidence_insufficient: false,
        refused: false,
        source: "gemini",
        demo: true,
      });
    }
    return json({ error: "not_found", message: "missing" }, 404);
  });
  globalThis.fetch = fetchMock as typeof fetch;

  render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Ask the assistant"), {
    target: { value: "What is the SYNTHETIC booking duration limit?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByText("Bookings last at most four hours in the SYNTHETIC notes.")).toBeInTheDocument();
  expect(screen.getByText(/synthetic booking guidelines, Duration/)).toBeInTheDocument();
  expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("/ai/assistant/query"))).toBe(true);
});

test("unavailable AI keeps the question visible instead of doing nothing", async () => {
  globalThis.fetch = vi.fn(async () =>
    json({ error: "unavailable", message: "AI is not configured." }, 503),
  ) as typeof fetch;

  render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );

  fireEvent.change(screen.getByLabelText("Ask the assistant"), {
    target: { value: "What is the SYNTHETIC booking duration limit?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByRole("heading", { name: "AI unavailable" })).toBeInTheDocument();
  expect(screen.getByText("What is the SYNTHETIC booking duration limit?", { selector: "p" })).toBeInTheDocument();
  expect(screen.getAllByText("AI is not configured.")).toHaveLength(2);
  await waitFor(() => {
    expect(screen.queryByText("Waiting for the API…")).not.toBeInTheDocument();
  });
});
