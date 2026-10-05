import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import ConfigurationNav from "./components/ConfigurationNav";
import Chat from "./pages/Chat";
import Servers from "./pages/Servers";
import Connections from "./pages/Connections";
import Automations from "./pages/Automations";
import Jobs from "./pages/Jobs";
import Monitoring from "./pages/Monitoring";
import Settings from "./pages/Settings";
import Login from "./pages/Login";
import { getToken } from "./lib/api";

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

function AppLayout() {
  const location = useLocation();

  const isConfigurationPage =
    location.pathname === "/servers" ||
    location.pathname === "/connections" ||
    location.pathname === "/automations" ||
    location.pathname === "/jobs" ||
    location.pathname === "/monitoring";

  return (
    <div className="flex">
      <Sidebar />

      <main className="flex-1 min-h-screen">
        {isConfigurationPage && <ConfigurationNav />}

        <Routes>
          <Route index element={<Chat />} />
          <Route path="servers" element={<Servers />} />
          <Route path="connections" element={<Connections />} />
          <Route path="automations" element={<Automations />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="monitoring" element={<Monitoring />} />
          <Route path="settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
