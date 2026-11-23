import { BrowserRouter, Route, Routes } from "react-router";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { AccessRequestsPage } from "./pages/AccessRequestsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { BookingsPage } from "./pages/BookingsPage";
import { EquipmentDetailPage } from "./pages/EquipmentDetailPage";
import { EquipmentPage } from "./pages/EquipmentPage";
import { HomePage } from "./pages/HomePage";
import { MatchingPage } from "./pages/MatchingPage";
import { NotFoundPage } from "./pages/NotFoundPage";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/equipment" element={<EquipmentPage />} />
      <Route path="/equipment/:equipmentId" element={<EquipmentDetailPage />} />
      <Route path="/matching" element={<MatchingPage />} />
      <Route path="/assistant" element={<AssistantPage />} />
      <Route path="/bookings" element={<BookingsPage />} />
      <Route path="/requests" element={<AccessRequestsPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ErrorBoundary>
  );
}
