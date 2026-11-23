import { Navigate, useLocation } from "react-router";
import type { ReactNode } from "react";
import { LoadingState } from "./LoadingState";
import { AppShell } from "../layouts/AppShell";
import { useAuth } from "../utilities/Auth";

type ProtectedRouteProps = {
  children: ReactNode;
  roles?: ReadonlyArray<"student" | "faculty" | "admin">;
};

export function ProtectedRoute({ children, roles }: ProtectedRouteProps) {
  const auth = useAuth();
  const location = useLocation();

  if (!auth.ready) {
    return (
      <AppShell title="LabLink">
        <LoadingState label="Checking session" />
      </AppShell>
    );
  }
  if (!auth.firebaseUser) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (roles && auth.profile && !roles.includes(auth.profile.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
