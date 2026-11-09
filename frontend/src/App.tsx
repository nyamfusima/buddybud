import type { ReactElement } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { CursorGlow, Loading, RobotCompanion } from "./components/Chrome";
import { AuthProvider, isManager, useAuth } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import type { Role } from "./lib/types";
import { AdminPage } from "./pages/Admin";
import { AgentHome } from "./pages/AgentHome";
import { ChangePasswordPage, ForgotPasswordPage, LoginPage, ResetPasswordPage } from "./pages/Auth";
import { InsightsPage } from "./pages/Insights";
import { AgentViewPage, TeamPage } from "./pages/Team";

function Protected({ roles, children }: { roles?: Role[]; children: ReactElement }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/welcome" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/" replace />;
  return <>{children}<RobotCompanion /></>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/welcome" replace />;
  if (user.role === "agent" || (user.agent_id && !isManager(user))) return <><AgentHome /><RobotCompanion /></>;
  return <Navigate to="/team" replace />;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <CursorGlow />
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/welcome" element={<ChangePasswordPage />} />
            <Route path="/" element={<Home />} />
            <Route path="/team" element={<Protected roles={["tl", "om", "admin"]}><TeamPage /></Protected>} />
            <Route path="/team/agent/:id" element={<Protected roles={["tl", "om", "admin"]}><AgentViewPage /></Protected>} />
            <Route path="/insights" element={<Protected roles={["om", "admin"]}><InsightsPage /></Protected>} />
            <Route path="/admin" element={<Protected roles={["admin"]}><AdminPage /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
