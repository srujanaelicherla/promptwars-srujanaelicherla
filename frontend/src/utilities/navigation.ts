export type NavItem = { href: string; label: string };

const publicNavigation: NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/equipment", label: "Book" },
  { href: "/matching", label: "Project Matching" },
  { href: "/assistant", label: "AI Assistant" },
];

export function navigationFor(signedIn: boolean, role: string | null): NavItem[] {
  const items = [...publicNavigation];
  if (signedIn) {
    items.push({ href: "/bookings", label: "My Bookings" });
    items.push({ href: "/requests", label: "Access Requests" });
  }
  if (role === "faculty" || role === "admin") {
    items.push({ href: "/dashboard", label: "Dashboard" });
    items.push({ href: "/faculty", label: "Faculty Review" });
  }
  return items;
}

export const primaryNavigation = publicNavigation;
