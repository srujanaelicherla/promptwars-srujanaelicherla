import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { App } from "./App";

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  globalThis.fetch = vi.fn(async () =>
    new Response(
      JSON.stringify({
        items: [],
        total: 0,
        limit: 100,
        offset: 0,
        source: "synthetic",
        demo: true,
      }),
      { headers: { "Content-Type": "application/json" } },
    ),
  ) as typeof fetch;
});

afterEach(() => {
  vi.restoreAllMocks();
});

test("renders the application shell with working navigation", () => {
  render(<App />);

  expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Skip to content" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Book" })).toHaveAttribute("href", "/equipment");
  expect(screen.getByRole("link", { name: "My Bookings" })).toHaveAttribute("href", "/bookings");
  expect(screen.getByRole("link", { name: "Access Requests" })).toHaveAttribute("href", "/requests");
  expect(screen.getByRole("link", { name: "Project Matching" })).toHaveAttribute("href", "/matching");
  expect(screen.getByRole("link", { name: "AI Assistant" })).toHaveAttribute("href", "/assistant");
  expect(screen.getByRole("link", { name: "Open AI Assistant" })).toHaveAttribute("href", "/assistant");
  expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Faculty dashboard" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Faculty Review" })).not.toBeInTheDocument();
  expect(screen.getByText("Synthetic catalog")).toBeInTheDocument();
});

test("menu button exposes and dismisses the navigation disclosure", () => {
  render(<App />);

  const openMenu = screen.getByRole("button", { name: "Menu" });
  expect(openMenu).toHaveAttribute("aria-expanded", "false");
  expect(openMenu).toHaveAttribute("aria-controls", "primary-navigation");

  fireEvent.click(openMenu);
  const closeMenu = screen.getByRole("button", { name: "Close" });
  expect(closeMenu).toHaveAttribute("aria-expanded", "true");

  fireEvent.keyDown(window, { key: "Escape" });
  const menu = screen.getByRole("button", { name: "Menu" });
  expect(menu).toHaveAttribute("aria-expanded", "false");
  expect(menu).toHaveFocus();
});

test("dashboard route is not a faculty sign-in wall", () => {
  window.history.pushState({}, "", "/dashboard");
  render(<App />);

  expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
});

test("unknown addresses render a not-found page", () => {
  window.history.pushState({}, "", "/not-a-page");
  render(<App />);

  expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to overview" })).toHaveAttribute("href", "/");
});
