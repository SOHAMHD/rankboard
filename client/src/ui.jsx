/* ════════════════════════════════════════════════════════════════════
   SHARED UI — design tokens and components every screen uses.

   Why split files now: one giant App.jsx was fine for a prototype,
   but each screen growing independently makes a single file painful
   to navigate and review. The rule of thumb: split when a file has
   more than one reason to change.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import { Eye, KeyRound, LoaderCircle, LogOut, Mail, Users, X } from "lucide-react";
import { api } from "./api";

export const ROLES = ["Super Admin", "Admin", "Team", "Client"];

// The ONE place mapping the report workflow's role concepts to the strings
// actually stored in users.role (mirrors server-python/app/permissions.py).
// Use ROLE.* and the flags below instead of sprinkling raw strings around.
export const ROLE = {
  ADMIN: "Super Admin",   // everything
  MANAGER: "Admin",       // all projects; authors + (later) sends reports
  TEAM_MEMBER: "Team",    // all projects; authors reports; can't send
  USER: "Client",         // scoped to assigned projects
};

// Convenience role flags derived from user.role. Report UI is NOT gated yet —
// these just make the role available the same way `can(user, action)` does.
export const isAdmin = (user) => user?.role === ROLE.ADMIN;
export const isManager = (user) => user?.role === ROLE.MANAGER;
export const isTeamMember = (user) => user?.role === ROLE.TEAM_MEMBER;
// Anyone who may author a report: manager, team member, or admin.
export const isAuthor = (user) => isAdmin(user) || isManager(user) || isTeamMember(user);
// May HARD-delete a report version (any status): Super Admin + Admin/Manager only.
// Mirrors server-python permissions.DELETER_ROLES; this only hides the control —
// the backend enforces the same set on the endpoint regardless.
export const isReportDeleter = (user) => isAdmin(user) || isManager(user);
// May SEND a report to a client: Super Admin + Admin/Manager only (NOT Team).
// Mirrors server-python permissions.SENDER_ROLES; hiding the control is a
// convenience — the /reports/{id}/send endpoint enforces the same set.
export const isReportSender = (user) => isAdmin(user) || isManager(user);

// Display labels for roles. The STORED value stays the raw role string
// (these are presentation only).
export const ROLE_LABELS = {
  "Super Admin": "Super Admin",
  "Admin": "Admin (Manager)",
  "Team": "Team Member",
  "Client": "Client",
};

export const roleLabel = (role) => ROLE_LABELS[role] || role;

export const ROLE_DESCRIPTIONS = {
  "Super Admin": "Full control. Onboards people and assigns roles.",
  "Admin": "Also called Manager. Full project control; authors reports and sends them to clients.",
  "Team": "Sees only assigned projects. Authors reports, but can't send them to clients.",
  "Client": "Permissions to be decided — most likely read-only.",
};

// A user is read-only when they can't author reports AND the server granted
// them no write permission at all (today: the Client role). Authors are never
// read-only. Derived from the permissions row + role so the "Read-only"
// indicator stays accurate now that Team is a write-capable author.
const WRITE_ACTIONS = ["manageUsers", "addProject", "toggleProject", "deleteProject", "addKeyword", "deleteKeyword"];
export const isReadOnly = (user) =>
  !!user && !isAuthor(user) && !WRITE_ACTIONS.some((a) => user.permissions?.[a]);

export const ROLE_STYLES = {
  "Super Admin": "bg-violet-100 text-violet-700",
  "Admin": "bg-sky-100 text-sky-700",
  "Team": "bg-teal-100 text-teal-700",
  "Client": "bg-stone-200 text-stone-600",
};

export const INPUT_CLS =
  "w-full rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-colors";

export const BTN_PRIMARY =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed";

export const BTN_GHOST =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-stone-300 hover:border-stone-400 bg-white text-stone-700 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500";

/* The client-side `can` reads the permissions object the SERVER sent
   with the user (from /api/auth/me). The matrix itself lives in one
   place — server/src/permissions.js — and the client just renders
   what it's told. Hiding a button here is UX; the API re-checks. */
export const can = (user, action) => !!user?.permissions?.[action];

export function TopBar({ user, onLogout, onPeople, onHome }) {
  const [showPw, setShowPw] = useState(false);
  return (
    <>
    <header className="bg-white border-b border-stone-200 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <button onClick={onHome} className="flex items-center gap-2.5 cursor-pointer" aria-label="Go to projects">
          <img src="/infapp-logo.png" alt="InfyApp" className="h-7 w-auto" />
          <span className="h-5 w-px bg-stone-200" aria-hidden="true" />
          <span className="font-bold text-stone-900 font-display">SEO Dashboard</span>
        </button>
        <div className="flex items-center gap-2 sm:gap-3">
          {onPeople && (can(user, "manageUsers") || can(user, "assignProjects")) && (
            <button
              onClick={onPeople}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-stone-600 hover:text-stone-900 px-2.5 py-1.5 rounded-lg hover:bg-stone-100 transition-colors"
            >
              <Users size={15} /> <span className="hidden sm:inline">People</span>
            </button>
          )}
          <span className="text-sm text-stone-600 hidden sm:inline">{user.name}</span>
          {isReadOnly(user) && (
            <span
              title="Your access is read-only — you can view everything but can't make changes."
              className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-stone-200 text-stone-600"
            >
              <Eye size={12} /> Read-only
            </span>
          )}
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_STYLES[user.role]}`}>{roleLabel(user.role)}</span>
          <button
            onClick={() => setShowPw(true)}
            aria-label="Change password"
            title="Change password"
            className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
          >
            <KeyRound size={16} />
          </button>
          <button
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out"
            className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors"
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
    {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}
    </>
  );
}

export function Modal({ title, onClose, children, wide }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0" style={{ backgroundColor: "rgba(15, 23, 42, 0.55)" }} onClick={onClose} />
      <div
        className={`relative w-full ${wide ? "max-w-md" : "max-w-sm"} bg-white rounded-2xl shadow-2xl p-6 max-h-full overflow-y-auto`}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-bold text-stone-900 font-display">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded-md text-stone-400 hover:text-stone-600 hover:bg-stone-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ErrorNote({ children }) {
  if (!children) return null;
  return (
    <p className="text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg px-3 py-2 mt-4">{children}</p>
  );
}

export function DarkShell({ children }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: "radial-gradient(70% 55% at 50% 0%, rgba(91,91,247,0.22), transparent 70%), #0f172a" }}
    >
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="rounded-xl bg-white px-3 py-2 flex items-center shadow-lg">
            <img src="/infapp-logo.png" alt="InfyApp" className="h-8 w-auto" />
          </div>
          <div>
            <p className="text-white font-semibold text-lg leading-tight font-display">SEO Dashboard</p>
            <p className="text-xs text-slate-400">Know where every keyword stands.</p>
          </div>
        </div>
        {children}
      </div>
    </div>
  );
}

export function Toggle({ on, onClick }) {
  return (
    <button
      onClick={onClick}
      role="switch"
      aria-checked={on}
      aria-label={on ? "Deactivate project" : "Activate project"}
      className={`relative h-6 w-11 rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 ${
        on ? "bg-blue-500" : "bg-stone-300"
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          on ? "translate-x-5" : ""
        }`}
      />
    </button>
  );
}


/* ── Change password: verify it's really you via an emailed one-time code,
   then set a new password. When the email step is frozen (local dev) the code
   step is skipped and the user sets a new password directly. ── */
export function ChangePasswordModal({ onClose }) {
  const [otpRequired, setOtpRequired] = useState(null); // null = still loading the config
  const [phase, setPhase] = useState("request"); // request | verify | done (OTP mode only)
  const [emailSentTo, setEmailSentTo] = useState(null);
  const [code, setCode] = useState("");
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/auth/config")
      .then((d) => setOtpRequired(!!d.passwordOtpRequired))
      .catch(() => setOtpRequired(true)); // safe default: require the code
  }, []);

  const requestCode = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api("/auth/password/request-code", { method: "POST" });
      setEmailSentTo(d.emailSentTo);
      setPhase("verify");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    if (pw1.length < 8) return setError("Password needs at least 8 characters.");
    if (pw1 !== pw2) return setError("The two passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      const body = otpRequired ? { code: code.trim(), newPassword: pw1 } : { newPassword: pw1 };
      await api("/auth/password/change", { method: "POST", body });
      setPhase("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const passwordFields = (
    <>
      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">New password</label>
      <input
        type="password"
          autoComplete="new-password"
        value={pw1}
        onChange={(e) => setPw1(e.target.value)}
        placeholder="At least 8 characters"
        autoFocus
        className={`${INPUT_CLS} mb-4`}
      />
      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Confirm new password</label>
      <input
        type="password"
          autoComplete="new-password"
        value={pw2}
        onChange={(e) => setPw2(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="Same again"
        className={INPUT_CLS}
      />
    </>
  );

  return (
    <Modal title="Change password" onClose={onClose} wide>
      {otpRequired === null ? (
        <div className="py-8 flex justify-center">
          <LoaderCircle size={20} className="text-orange-600 animate-spin" />
        </div>
      ) : phase === "done" ? (
        <>
          <p className="text-sm text-stone-600 -mt-0.5 mb-4">
            Your password has been changed. Use the new one next time you sign in.
          </p>
          <button onClick={onClose} className={`${BTN_PRIMARY} w-full py-2.5`}>Done</button>
        </>
      ) : !otpRequired ? (
        <>
          <p className="text-sm text-stone-500 -mt-0.5 mb-4">Choose a new password.</p>
          {passwordFields}
          <ErrorNote>{error}</ErrorNote>
          <button onClick={submit} disabled={busy || !pw1 || !pw2} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Update password"}
          </button>
        </>
      ) : phase === "request" ? (
        <>
          <p className="text-sm text-stone-500 -mt-0.5 mb-4">
            For your security we'll email you a one-time code to confirm it's you, then you can set a new password.
          </p>
          <ErrorNote>{error}</ErrorNote>
          <button onClick={requestCode} disabled={busy} className={`${BTN_PRIMARY} w-full mt-2 py-2.5`}>
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : (<><Mail size={15} /> Email me a code</>)}
          </button>
        </>
      ) : (
        <>
          <p className="text-sm text-stone-500 -mt-0.5 mb-4">
            Enter the 6-digit code we sent to {emailSentTo || "your email"}, then choose a new password.
          </p>
          <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Code</label>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="123456"
            autoFocus
            className={`${INPUT_CLS} mb-4 text-center tracking-[0.4em]`}
          />
          {passwordFields}
          <ErrorNote>{error}</ErrorNote>
          <button onClick={submit} disabled={busy || !code || !pw1 || !pw2} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Update password"}
          </button>
          <button onClick={requestCode} disabled={busy} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
            Resend code
          </button>
        </>
      )}
    </Modal>
  );
}
