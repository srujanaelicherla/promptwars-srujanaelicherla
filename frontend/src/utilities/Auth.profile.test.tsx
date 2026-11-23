import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { App } from "../App";
import {
  INVALID_CREDENTIAL_MESSAGE,
  MISSING_PROFILE_MESSAGE,
  SESSION_EXPIRED_MESSAGE,
} from "./api";

const { fakeUser, signOutMock } = vi.hoisted(() => ({
  fakeUser: {
    uid: "firebase-uid-example",
    email: "student@example.com",
    getIdToken: async () => "aaa.bbb.ccc",
  },
  signOutMock: vi.fn(async () => {}),
}));

vi.mock("./firebase", () => ({
  firebaseConfigured: () => true,
  getFirebaseAuth: () => ({ currentUser: fakeUser }),
}));

vi.mock("@firebase/auth", () => ({
  onAuthStateChanged: (_auth: unknown, callback: (user: typeof fakeUser | null) => void) => {
    callback(fakeUser);
    return () => {};
  },
  signInWithEmailAndPassword: vi.fn(),
  createUserWithEmailAndPassword: vi.fn(async () => ({ user: fakeUser })),
  signOut: signOutMock,
}));

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const studentProfile = {
  id: "firebase-uid-example",
  role: "student",
  department_id: "dept-biology",
  auth: "firebase",
  demo: true,
};

afterEach(() => {
  vi.restoreAllMocks();
  signOutMock.mockClear();
});

beforeEach(() => {
  window.history.replaceState({}, "", "/assistant");
});

test("existing signed-in user with no profile completes student bootstrap", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/me")) {
      return json({ error: "unauthorized", message: MISSING_PROFILE_MESSAGE }, 401);
    }
    if (url.includes("/users/bootstrap")) {
      const payload = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      expect(payload).toEqual({ department_id: "dept-biology" });
      expect(init?.headers).toEqual(expect.objectContaining({ Authorization: "Bearer aaa.bbb.ccc" }));
      return json(studentProfile, 201);
    }
    return json({ items: [], total: 0, limit: 100, offset: 0, source: "synthetic" });
  });
  globalThis.fetch = fetchMock as typeof fetch;

  render(<App />);

  expect(await screen.findByText("student@example.com · signed in")).toBeInTheDocument();
  expect(screen.getByText(/You are signed in as student@example.com/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Finish student profile" })).toBeInTheDocument();
  expect(screen.queryByText(/session expired/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/sign in again/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Sign in required" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "My Bookings" })).toBeInTheDocument();
  expect(screen.getByLabelText("Ask the assistant")).not.toBeDisabled();

  fireEvent.change(screen.getByLabelText("Department"), { target: { value: "dept-biology" } });
  fireEvent.click(screen.getByRole("button", { name: "Create student profile" }));

  await waitFor(() => {
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("/users/bootstrap"))).toBe(true);
  });
  expect(signOutMock).not.toHaveBeenCalled();
  expect(await screen.findByText(/student@example.com · student/)).toBeInTheDocument();
});

test("new registration posts student bootstrap without a role field", async () => {
  const { createUserWithEmailAndPassword } = await import("@firebase/auth");
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/me")) {
      return json({ error: "unauthorized", message: MISSING_PROFILE_MESSAGE }, 401);
    }
    if (url.includes("/users/bootstrap")) {
      expect(JSON.parse(String(init?.body ?? "{}"))).toEqual({ department_id: "dept-physics" });
      return json({ ...studentProfile, department_id: "dept-physics" }, 201);
    }
    return json({ items: [], total: 0, limit: 100, offset: 0, source: "synthetic" });
  });
  globalThis.fetch = fetchMock as typeof fetch;
  window.history.replaceState({}, "", "/register");

  render(<App />);

  fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "student@example.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password1" } });
  const departmentFields = screen.getAllByLabelText("Department");
  const registerDepartment = departmentFields[departmentFields.length - 1];
  expect(registerDepartment).toBeDefined();
  fireEvent.change(registerDepartment as HTMLSelectElement, { target: { value: "dept-physics" } });
  fireEvent.click(screen.getByRole("button", { name: "Register as student" }));

  await waitFor(() => {
    expect(createUserWithEmailAndPassword).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("/users/bootstrap"))).toBe(true);
  });
  expect(signOutMock).not.toHaveBeenCalled();
});

test("invalid Firebase credential shows session expired and does not keep a profile form", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/me")) {
      return json({ error: "unauthorized", message: INVALID_CREDENTIAL_MESSAGE }, 401);
    }
    return json({ items: [], total: 0, limit: 100, offset: 0, source: "synthetic" });
  }) as typeof fetch;

  render(<App />);

  expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
  expect(screen.getByText(/sign in again/i)).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Finish student profile" })).not.toBeInTheDocument();
  expect(signOutMock).toHaveBeenCalled();
});

test("expired Firebase credential is the only session-expired path", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/me")) {
      return json({ error: "unauthorized", message: SESSION_EXPIRED_MESSAGE }, 401);
    }
    return json({ items: [], total: 0, limit: 100, offset: 0, source: "synthetic" });
  }) as typeof fetch;

  render(<App />);

  expect(await screen.findByText(/session expired/i)).toBeInTheDocument();
  expect(signOutMock).toHaveBeenCalled();
});

test("authenticated navigation stays available with a loaded student profile", async () => {
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/me")) {
      return json(studentProfile);
    }
    return json({ items: [], total: 0, limit: 100, offset: 0, source: "synthetic" });
  }) as typeof fetch;
  window.history.replaceState({}, "", "/");

  render(<App />);

  expect(await screen.findByText(/student@example.com · student/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "My Bookings" })).toHaveAttribute("href", "/bookings");
  expect(screen.getByRole("link", { name: "Access Requests" })).toHaveAttribute("href", "/requests");
  expect(screen.queryByRole("link", { name: "Faculty Review" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Finish student profile" })).not.toBeInTheDocument();
  expect(signOutMock).not.toHaveBeenCalled();
});
