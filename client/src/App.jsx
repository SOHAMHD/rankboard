import { lazy, Suspense, useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { api, getToken, setToken, SESSION_EXPIRED } from "./api";
import { can, BTN_PRIMARY, DarkShell } from "./ui";
import { useToast } from "./toast.jsx";
import { LoginView, SetPasswordView, TwoFactorView } from "./screens/Auth.jsx";
import { ProjectsView } from "./screens/Projects.jsx";

const ProjectDashboard = lazy(() =>
  import("./screens/Dashboard.jsx").then((m) => ({ default: m.ProjectDashboard }))
);
const AdminPanelView = lazy(() =>
  import("./screens/AdminPanel.jsx").then((m) => ({ default: m.AdminPanelView }))
);
const EmailLogView = lazy(() =>
  import("./screens/EmailLog.jsx").then((m) => ({ default: m.EmailLogView }))
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
  const [unreachable, setUnreachable] = useState(false);

  const bootstrap = () => {
    if (!getToken()) {
      setBooting(false);
      return;
    }
    setBooting(true);
    setUnreachable(false);
    api("/auth/me")
      .then((d) => {
        setUser(d.user);
        setTwofa(d.twofa);
      })
      .catch((err) => {
        // Only a 401 means the token is genuinely no good. Clearing it on any
        // failure signed everybody out the moment the backend restarted or a
        // proxy returned a 502 — the session was fine, the network wasn't.
        if (err?.status === 401) {
          setToken(null);
        } else {
          setUnreachable(true);
        }
      })
      .finally(() => setBooting(false));
  };

  useEffect(() => {
    bootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The token lasts 8 hours, so it routinely expires while someone is using the
  // app. api() clears it and fires this on the first 401; without the listener
  // the app stayed "signed in" and every screen just failed in its own quiet way.
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setTwofa(null);
      setOpenProjectId(null);
      setView("projects");
      toast.error("Your session expired. Please sign in again.", { title: "Signed out" });
    };
    window.addEventListener(SESSION_EXPIRED, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED, onExpired);
  }, [toast]);

  // Warm the Dashboard chunk, but only once the browser is actually idle and not
  // on a connection where the extra download would hurt. A fixed 1200ms timer
  // fired while the projects list was still loading, so the prefetch competed
  // for bandwidth with the data the user was waiting to see.
  useEffect(() => {
    if (!user) return;
    const conn = navigator.connection;
    if (conn && (conn.saveData || /(^|-)2g$/.test(conn.effectiveType || ""))) return;

    const prefetch = () => import("./screens/Dashboard.jsx");
    if (typeof requestIdleCallback === "function") {
      const handle = requestIdleCallback(prefetch, { timeout: 4000 });
      return () => cancelIdleCallback(handle);
    }
    const t = setTimeout(prefetch, 2500);
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

  // The token is still valid as far as we know — we simply couldn't reach the
  // server to confirm it. Showing the login screen here would be a lie, and
  // would tempt the user into signing in again against a server that's down.
  if (unreachable && !user) {
    return (
      <DarkShell>
        <div className="bg-white rounded-2xl shadow-2xl p-6 text-center">
          <h1 className="text-lg font-bold text-stone-900 font-display">Can&apos;t reach the server</h1>
          <p className="text-sm text-stone-500 mt-2">
            You&apos;re still signed in — the dashboard just couldn&apos;t load. Check your
            connection and try again.
          </p>
          <button onClick={bootstrap} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            Try again
          </button>
          <button
            onClick={logout}
            className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors"
          >
            Sign out instead
          </button>
        </div>
      </DarkShell>
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
        <AdminPanelView
          user={user}
          onBack={() => setView("projects")}
          onEmailLog={() => setView("emailLog")}
          onLogout={logout}
        />
      </Suspense>
    );
  }

  // Super Admin only. This is a second gate, not the gate: the server checks
  // `viewEmailLog` on every /email-log route, so hiding the screen here is a
  // courtesy to the UI rather than the thing keeping other roles out.
  if (view === "emailLog" && can(user, "viewEmailLog")) {
    return (
      <Suspense fallback={<FullScreenLoader />}>
        <EmailLogView
          user={user}
          onBack={() => setView("projects")}
          onPeople={() => setView("people")}
          onLogout={logout}
        />
      </Suspense>
    );
  }

  return (
    <ProjectsView
      user={user}
      onOpenProject={setOpenProjectId}
      onPeople={() => setView("people")}
      onEmailLog={() => setView("emailLog")}
      onLogout={logout}
    />
  );
}
