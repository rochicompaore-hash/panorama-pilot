import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { useAuth } from "@/contexts/AuthContext";
import Login from "@/pages/Login";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import AcceptInvitation from "@/pages/AcceptInvitation";
import ChangePassword from "@/pages/ChangePassword";
import Dashboard from "@/pages/Dashboard";
import UsersPage from "@/pages/UsersPage";
import RolesPage from "@/pages/RolesPage";
import CompanyPage from "@/pages/CompanyPage";
import SequencesPage from "@/pages/SequencesPage";
import AttachmentsPage from "@/pages/AttachmentsPage";
import AuditPage from "@/pages/AuditPage";
import NotificationsPage from "@/pages/NotificationsPage";
import SessionsPage from "@/pages/SessionsPage";
import EmailLogsPage from "@/pages/EmailLogsPage";
import SearchPage from "@/pages/SearchPage";
import AppLayout from "@/layouts/AppLayout";

function Protected({ children }) {
  const { user } = useAuth();
  if (user === undefined) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="overline" data-testid="app-loading">Caricamento…</div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return children;
}

function App() {
  return (
    <div className="App">
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/accept-invitation" element={<AcceptInvitation />} />
        <Route path="/change-password" element={<ChangePassword />} />
        <Route
          path="/"
          element={
            <Protected>
              <AppLayout />
            </Protected>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="company" element={<CompanyPage />} />
          <Route path="sequences" element={<SequencesPage />} />
          <Route path="attachments" element={<AttachmentsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="email-logs" element={<EmailLogsPage />} />
          <Route path="search" element={<SearchPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}

export default App;
