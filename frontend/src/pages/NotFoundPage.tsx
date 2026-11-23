import { Link } from "react-router";
import { ErrorState } from "../components/ErrorState";
import { AppShell } from "../layouts/AppShell";
import { textLinkClassName } from "../utilities/classes";
import { usePageTitle } from "../utilities/usePageTitle";

export function NotFoundPage() {
  usePageTitle("Page not found · LabLink");

  return (
    <AppShell title="Page not found">
      <ErrorState
        title="Page not found"
        message="This address is not part of the LabLink application shell."
      >
        <Link className={textLinkClassName} to="/">
          Back to overview
        </Link>
      </ErrorState>
    </AppShell>
  );
}
