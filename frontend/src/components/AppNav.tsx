import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router";
import { useAuth } from "../utilities/Auth";
import { navigationFor } from "../utilities/navigation";
import { SkipLink } from "./SkipLink";

const navigationId = "primary-navigation";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  [
    "inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium",
    isActive ? "bg-accent text-on-primary" : "text-mist hover:bg-accent/40",
  ].join(" ");

export function AppNav() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const auth = useAuth();
  const items = navigationFor(Boolean(auth.firebaseUser), auth.profile?.role ?? null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape") {
        return;
      }
      setMenuOpen(false);
      menuButtonRef.current?.focus();
    }

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const navigationClassName = menuOpen
    ? "flex flex-col gap-1 p-3 md:flex"
    : "hidden flex-col gap-1 p-3 md:flex";

  return (
    <div className="site-nav bg-primary text-on-primary md:min-h-screen">
      <SkipLink />
      <div className="flex items-center justify-between px-4 py-4 md:block">
        <NavLink to="/" className="font-display text-2xl tracking-tight text-on-primary" aria-label="LabLink home">
          LabLink
        </NavLink>
        <p className="mt-1 hidden text-sm text-mist md:block">University laboratories</p>
        <button
          ref={menuButtonRef}
          type="button"
          className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-sm font-medium md:hidden"
          aria-expanded={menuOpen}
          aria-controls={navigationId}
          onClick={() => {
            setMenuOpen((open) => !open);
          }}
        >
          {menuOpen ? "Close" : "Menu"}
        </button>
      </div>
      <nav id={navigationId} aria-label="Primary" className={navigationClassName}>
        {items.map((item) => (
          <NavLink
            key={item.href}
            to={item.href}
            className={linkClass}
            end={item.href === "/"}
            onClick={() => {
              setMenuOpen(false);
            }}
          >
            {item.label}
          </NavLink>
        ))}
        {auth.firebaseUser ? null : (
          <NavLink to="/login" className={linkClass} onClick={() => setMenuOpen(false)}>
            Sign in
          </NavLink>
        )}
      </nav>
    </div>
  );
}
