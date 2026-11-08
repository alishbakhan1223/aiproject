import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import ProtectedRoute from "./components/ProtectedRoute";
import AdminNav from "./components/AdminNav";
import UserNav from "./components/UserNav";

import Login from "./pages/Login";
import DashboardPage from "./pages/DashboardPage";
import EventsPage from "./pages/EventsPage";
import AlertsPage from "./pages/AlertsPage";
import PersonsPage from "./pages/PersonsPage";
import UnknownReviewPage from "./pages/UnknownReviewPage";
import ZoneEditorPage from "./pages/ZoneEditorPage";
import StatsPage from "./pages/StatsPage";
import HealthPage from "./pages/HealthPage";
import UsersPage from "./pages/UsersPage";
import UserHomePage from "./pages/UserHomePage";
import SpecUnknownsPage from "./pages/SpecUnknownsPage";

function AppShell({ children }) {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-950 text-gray-100 flex items-center justify-center">
        Loading...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      {isAuthenticated && (isAdmin ? <AdminNav /> : <UserNav />)}
      {children}
    </div>
  );
}

function RootRedirect() {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  if (isLoading) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return isAdmin ? <Navigate to="/dashboard" replace /> : <Navigate to="/user/home" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppShell>
          <Routes>
            {/* Public */}
            <Route path="/login" element={<Login />} />

            {/* Admin Routes */}
            <Route path="/dashboard" element={<ProtectedRoute requireAdmin><DashboardPage /></ProtectedRoute>} />
            <Route path="/persons" element={<ProtectedRoute requireAdmin><PersonsPage /></ProtectedRoute>} />
            <Route path="/unknown-persons" element={<ProtectedRoute requireAdmin><UnknownReviewPage /></ProtectedRoute>} />
            <Route path="/unknown-review" element={<ProtectedRoute requireAdmin><UnknownReviewPage /></ProtectedRoute>} />
            <Route path="/zone-editor" element={<ProtectedRoute requireAdmin><ZoneEditorPage /></ProtectedRoute>} />
            <Route path="/events" element={<ProtectedRoute requireAdmin><EventsPage /></ProtectedRoute>} />
            <Route path="/alerts" element={<ProtectedRoute requireAdmin><AlertsPage /></ProtectedRoute>} />
            <Route path="/health" element={<ProtectedRoute requireAdmin><HealthPage /></ProtectedRoute>} />
            <Route path="/stats" element={<ProtectedRoute requireAdmin><StatsPage /></ProtectedRoute>} />
            <Route path="/users" element={<ProtectedRoute requireAdmin><UsersPage /></ProtectedRoute>} />
            <Route path="/spec-unknowns" element={<ProtectedRoute requireAdmin><SpecUnknownsPage /></ProtectedRoute>} />

            {/* User Routes */}
            <Route path="/user/home" element={<ProtectedRoute><UserHomePage /></ProtectedRoute>} />
            <Route path="/user/people/add" element={<ProtectedRoute><PersonsPage /></ProtectedRoute>} />
            <Route path="/user/people/promote" element={<ProtectedRoute><UnknownReviewPage /></ProtectedRoute>} />

            {/* Redirects */}
            <Route path="/" element={<RootRedirect />} />
            <Route path="*" element={<RootRedirect />} />
          </Routes>
        </AppShell>
      </AuthProvider>
    </BrowserRouter>
  );
}