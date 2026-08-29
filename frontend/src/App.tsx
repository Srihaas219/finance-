import { Navigate, Route, Routes } from "react-router-dom";
import ConsumerDashboard from "./pages/ConsumerDashboard";
import OperatorDashboard from "./pages/OperatorDashboard";
import ReviewerDashboard from "./pages/ReviewerDashboard";
import Login from "./pages/Login";
import { useAuth } from "./lib/auth";
import type { Role } from "./lib/api";

function Protected({ role, children }: { role: Role; children: JSX.Element }) {
  const { token, role: userRole } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  if (userRole !== role) return <Navigate to={`/${userRole?.replace("data_", "")}`} replace />;
  return children;
}

function Home() {
  const { token, role } = useAuth();
  if (!token || !role) return <Navigate to="/login" replace />;
  const dest = role === "data_operator" ? "/operator" : role === "reviewer" ? "/reviewer" : "/consumer";
  return <Navigate to={dest} replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/operator"
        element={
          <Protected role="data_operator">
            <OperatorDashboard />
          </Protected>
        }
      />
      <Route
        path="/reviewer"
        element={
          <Protected role="reviewer">
            <ReviewerDashboard />
          </Protected>
        }
      />
      <Route
        path="/consumer"
        element={
          <Protected role="data_consumer">
            <ConsumerDashboard />
          </Protected>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
