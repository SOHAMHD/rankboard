/* ════════════════════════════════════════════════════════════════════
   APP — the state machine, now just a thin coordinator.

   Each screen lives in its own module and owns its own data fetching;
   this file only decides WHICH screen renders:

     no user                → Login
     mustChangePassword     → forced password change
     openProjectId set      → that project's dashboard
     view === "people"      → admin panel (if permitted)
     otherwise              → Projects (the main landing page)
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api, getToken, setToken } from "./api";
import { can } from "./ui";
import { LoginView, SetPasswordView } from "./screens/Auth.jsx";
import { ProjectsView } from "./screens/Projects.jsx";
import { ProjectDashboard } from "./screens/Dashboard.jsx";
import { AdminPanelView } from "./screens/AdminPanel.jsx";

export default function App() {
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [view, setView] = useState("projects"); // "projects" | "people"
  const [openProjectId, setOpenProjectId] = useState(null);

  // On load: if a token is saved, ask the server who we are, so a
  // page refresh doesn't log the user out.
  useEffect(() => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api("/auth/me")
      .then((d) => setUser(d.user))
      .catch(() => setToken(null))
      .finally(() => setBooting(false));
  }, []);

  const handleLogin = async (email, password) => {
    const d = await api("/auth/login", { method: "POST", body: { email, password } });
    setToken(d.token);
    setUser(d.user); // includes the permissions object from the server
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setView("projects");
    setOpenProjectId(null);
  };

  if (booting) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-stone-100">
        <LoaderCircle size={24} className="text-orange-600 animate-spin" />
      </div>
    );
  }

  if (!user) return <LoginView onLogin={handleLogin} />;

  if (user.mustChangePassword) {
    return (
      <SetPasswordView
        user={user}
        onDone={async () => {
          const d = await api("/auth/me");
          setUser(d.user);
        }}
        onLogout={logout}
      />
    );
  }

  if (openProjectId) {
    return (
      <ProjectDashboard
        user={user}
        projectId={openProjectId}
        onBack={() => setOpenProjectId(null)}
        onLogout={logout}
      />
    );
  }

  if (view === "people" && can(user, "manageUsers")) {
    return <AdminPanelView user={user} onBack={() => setView("projects")} onLogout={logout} />;
  }

  return (
    <ProjectsView
      user={user}
      onOpenProject={setOpenProjectId}
      onPeople={() => setView("people")}
      onLogout={logout}
    />
  );
}
