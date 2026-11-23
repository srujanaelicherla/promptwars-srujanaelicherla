import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";
import { AssistantPage } from "./AssistantPage";

const authState = vi.hoisted(() => ({
  value: {
    ready: true,
    configured: true,
    firebaseUser: null as { uid: string; email: string } | null,
    profile: null as {
      id: string;
      role: "student";
      department_id: string;
      auth: "firebase";
      demo: true;
    } | null,
    needsProfile: false,
    error: null as string | null,
    expired: false,
    signIn: async () => {},
    register: async () => {},
    completeStudentProfile: async () => {},
    signOut: async () => {},
  },
}));

vi.mock("../utilities/Auth", () => ({
  useAuth: () => authState.value,
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("../utilities/firebase", () => ({
  firebaseConfigured: () => true,
  getFirebaseAuth: () => (authState.value.firebaseUser ? { currentUser: authState.value.firebaseUser } : null),
}));

const student = { uid: "firebase-uid-example", email: "student@example.com" };
const profile = {
  id: "firebase-uid-example",
  role: "student" as const,
  department_id: "dept-physics",
  auth: "firebase" as const,
  demo: true as const,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  authState.value.firebaseUser = null;
  authState.value.profile = null;
  authState.value.needsProfile = false;
});

test("assistant page is visible with examples and a sign-in state", () => {
  render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { level: 1, name: "LabLink AI Assistant" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Example questions" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /SYNTHETIC booking duration/ })).toBeDisabled();
  expect(screen.getByRole("heading", { name: "Sign in required" })).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByText("Project description")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Extract requirements" })).not.toBeInTheDocument();
});

test("missing profile blocks send and tells the user to finish setup", async () => {
  authState.value.firebaseUser = student;
  authState.value.needsProfile = true;
  const fetchMock = vi.fn();
  globalThis.fetch = fetchMock as typeof fetch;

  render(
    <MemoryRouter>
      <AssistantPage />
    </MemoryRouter>,
  );

  expect(screen.getByRole("heading", { name: "Student profile required" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Ask the assistant"), {
    target: { value: "What is the SYNTHETIC booking duration limit?" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send question" }));

  expect(await screen.findByRole("heading", { name: "Assistant error" })).toBeInTheDocument();
  expect(screen.getAllByText(/Finish the student profile form above/)).toHaveLength(2);
  expect(fetchMock).not.toHaveBeenCalled();
});

test("signed-in user with a profile sends a question and renders a cited answer", async () => {
  authState.value.firebaseUser = student;
  authState.value.profile = profile;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/ai/assistant/query")) {
      expect(init?.method).toBe("POST");
      expect(JSON.parse(String(init?.body ?? "{}"))).toEqual({
        question: "What is the SYNTHETIC booking duration limit?",
      });
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
  authState.value.firebaseUser = student;
  authState.value.profile = profile;
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
