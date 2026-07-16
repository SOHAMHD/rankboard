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
import { lazy, Suspense, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api, getToken, setToken } from "./api";
import { can } from "./ui";
import { useToast } from "./toast.jsx";
import { LoginView, SetPasswordView, TwoFactorView } from "./screens/Auth.jsx";
import { ProjectsView } from "./screens/Projects.jsx";

// The two heaviest screens are code-split so they aren't in the initial bundle:
// Dashboard pulls in Recharts + the TipTap report editors, and AdminPanel is
// only reachable by admins. They load on demand behind the <Suspense> fallback.
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
  const [view, setView] = useState("projects"); // "projects" | "people"
  const [openProjectId, setOpenProjectId] = useState(null);
  const [twofa, setTwofa] = useState(null); // {required, enrolled, verified} from login/me

  // On load: if a token is saved, ask the server who we are, so a
  // page refresh doesn't log the user out.
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

  // Warm the code-split Dashboard chunk in the background once signed in, so
  // opening a project does not stall on a lazy-load fetch.
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
      setUser(d.user); // includes the permissions object from the server
      setTwofa(d.twofa); // {required, enrolled, verified:false} — gates access below
      // If 2FA still stands between them and the app, say so; otherwise welcome.
      if (d.twofa && d.twofa.required && !d.twofa.verified) {
        toast.info("Password accepted — one more step to finish signing in.");
      } else {
        toast.success(`Welcome back, ${d.user?.name?.split(" ")[0] || "there"}.`, { title: "Signed in" });
      }
    } catch (err) {
      toast.error(err.message || "Login failed.", { title: "Sign-in failed" });
      throw err; // let LoginView still show its inline error
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

  // Called when the authenticator (or a backup) code checks out: swap the
  // pending token for the verified one and let the app render.
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
