import { lazy, Suspense, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api, getToken, setToken } from "./api";
import { can } from "./ui";
import { useToast } from "./toast.jsx";
import { LoginView, SetPasswordView, TwoFactorView } from "./screens/Auth.jsx";
import { ProjectsView } from "./screens/Projects.jsx";

const ProjectDashboard = lazy(() =>
  import("./screens/Dashboard.jsx").then((m) => ({ default: m.ProjectDashboard }))
);
const AdminPanelView = lazy(() =>
  import("./screens/AdminPanel.jsx").then((m) => ({ default: m.AdminPanelView }))
);

function FullScreenLoader() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-stone-100">
      <LoaderCircle size={24} className="text-orange-600 animate-spin" />
    </div>
  );
}

export default function App() {
  const toast = useToast();
  const [user, setUser] = useState(null);
  const [booting, setBooting] = useState(true);
  const [view, setView] = useState("projects");
  const [openProjectId, setOpenProjectId] = useState(null);
  const [twofa, setTwofa] = useState(null);

  useEffect(() => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    api("/auth/me")
      .then((d) => {
        setUser(d.user);
        setTwofa(d.twofa);
      })
      .catch(() => setToken(null))
      .finally(() => setBooting(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    const t = setTimeout(() => {
      import("./screens/Dashboard.jsx");
    }, 1200);
    return () => clearTimeout(t);
  }, [user]);

  const handleLogin = async (email, password) => {
    try {
      const d = await api("/auth/login", { method: "POST", body: { email, password } });
      setToken(d.token);
      setUser(d.user);
      setTwofa(d.twofa);
      if (d.twofa && d.twofa.required && !d.twofa.verified) {
        toast.info("Password accepted — one more step to finish signing in.");
      } else {
        toast.success(`Welcome back, ${d.user?.name?.split(" ")[0] || "there"}.`, { title: "Signed in" });
      }
    } catch (err) {
      toast.error(err.message || "Login failed.", { title: "Sign-in failed" });
      throw err;
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    setTwofa(null);
    setView("projects");
    setOpenProjectId(null);
    toast.info("You've been signed out.");
  };

  const handle2faVerified = (token, u) => {
    setToken(token);
    setUser(u);
    setTwofa({ required: true, enrolled: true, verified: true });
    toast.success(`Welcome back, ${u?.name?.split(" ")[0] || "there"}.`, { title: "Signed in" });
  };

  if (booting) return <FullScreenLoader />;

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

  if (twofa && twofa.required && !twofa.verified) {
    return (
      <TwoFactorView
        user={user}
        enrolled={twofa.enrolled}
        onVerified={handle2faVerified}
        onLogout={logout}
      />
    );
  }

  if (openProjectId) {
    return (
      <Suspense fallback={<FullScreenLoader />}>
        <ProjectDashboard
          user={user}
          projectId={openProjectId}
          onBack={() => setOpenProjectId(null)}
          onLogout={logout}
        />
      </Suspense>
    );
  }

  if (view === "people" && (can(user, "manageUsers") || can(user, "assignProjects"))) {
    return (
      <Suspense fallback={<FullScreenLoader />}>
        <AdminPanelView user={user} onBack={() => setView("projects")} onLogout={logout} />
      </Suspense>
    );
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
