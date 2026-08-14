import { useEffect, useRef, useState } from "react";
import { Eye, KeyRound, LoaderCircle, LogOut, Mail, MailCheck, Trash2, Users, X } from "lucide-react";
import { api, setToken } from "./api";

export const ROLES = ["Super Admin", "Admin", "Team", "Client"];

/**
 * A wizard-only pseudo-role for a client who receives reports but never signs in.
 *
 * It is NOT a real role: the server rejects anything outside ROLES, and nothing
 * is written to `users` on this path — only `project_recipients`. Kept out of
 * ROLES on purpose so role dropdowns, permission checks and the users table
 * can't accidentally offer it.
 */
export const CONTACT_ONLY = "Client contact";

export const ROLE = {
  ADMIN: "Super Admin",
  MANAGER: "Admin",
  TEAM_MEMBER: "Team",
  USER: "Client",
};

export const isAdmin = (user) => user?.role === ROLE.ADMIN;
export const isManager = (user) => user?.role === ROLE.MANAGER;
// Not exported: nothing outside this file asks "is this a team member?" — only
// isAuthor below needs it.
const isTeamMember = (user) => user?.role === ROLE.TEAM_MEMBER;
export const isAuthor = (user) => isAdmin(user) || isManager(user) || isTeamMember(user);
// Team included: they author reports, so clearing up a mis-generated draft
// shouldn't need an Admin. Mirrors DELETER_ROLES in permissions.py — the server is
// the actual gate, this only decides whether the button is drawn.
export const isReportDeleter = (user) => isAdmin(user) || isManager(user) || isTeamMember(user);
// Sending stays Admin-only. A deleted report can be regenerated; an email to a
// client can't be recalled.
export const isReportSender = (user) => isAdmin(user) || isManager(user);

export const ROLE_LABELS = {
  "Super Admin": "Super Admin",
  "Admin": "Admin (Manager)",
  "Team": "Team Member",
  "Client": "Client with dashboard access",
  "Client contact": "Client contact only",
};

export const roleLabel = (role) => ROLE_LABELS[role] || role;

export const ROLE_DESCRIPTIONS = {
  "Super Admin": "Full control. Onboards people and assigns roles.",
  "Admin": "Also called Manager. Full project control; authors reports and sends them to clients.",
  "Team": "Sees only assigned projects. Authors reports, but can't send them to clients.",
  "Client": "Signs in to see their own project, and receives reports by email.",
  "Client contact": "Receives reports by email only. No account, no invite email.",
};

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

export const can = (user, action) => !!user?.permissions?.[action];

export function TopBar({ user, onLogout, onPeople, onEmailLog, onHome }) {
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
          {onEmailLog && can(user, "viewEmailLog") && (
            <button
              onClick={onEmailLog}
              title="Every email the system has sent, and what happened to it"
              className="inline-flex items-center gap-1.5 text-sm font-medium text-stone-600 hover:text-stone-900 px-2.5 py-1.5 rounded-lg hover:bg-stone-100 transition-colors"
            >
              <MailCheck size={15} /> <span className="hidden sm:inline">Email Log</span>
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

let modalSeq = 0;

/**
 * The app's one dialog implementation.
 *
 * It previously had no `role`, no `aria-modal`, no Escape handler, no focus trap
 * and no focus restore — so a keyboard or screen-reader user could Tab straight
 * out of an "open" dialog into the page behind it and never find the close
 * button. It also closed on any backdrop click, which meant a stray click behind
 * the five-step onboarding wizard discarded name, email, project selection and
 * per-project recipients with no confirmation. Hence `dismissOnBackdrop`.
 */
export function Modal({ title, onClose, children, wide, dismissOnBackdrop = true }) {
  const panelRef = useRef(null);
  const titleId = useRef(`modal-title-${++modalSeq}`).current;

  useEffect(() => {
    const previouslyFocused = document.activeElement;
    // Focus the panel itself rather than the first control: reading the title
    // before the fields is the point of announcing a dialog.
    panelRef.current?.focus();

    // The page behind must not scroll while a dialog is over it.
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose?.();
        return;
      }
      if (e.key !== "Tab") return;

      // Keep Tab inside the dialog. Without this the browser walks into the page
      // behind, where every control is still focusable.
      const focusable = panelRef.current?.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (!focusable || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = prevOverflow;
      // Send focus back where it came from, so closing a dialog doesn't dump the
      // user at the top of the document.
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(15, 23, 42, 0.55)" }}
        onClick={dismissOnBackdrop ? onClose : undefined}
      />
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={`relative w-full ${wide ? "max-w-md" : "max-w-sm"} bg-white rounded-2xl shadow-2xl p-6 max-h-full overflow-y-auto focus:outline-none`}
      >
        <div className="flex items-center justify-between mb-1">
          <h2 id={titleId} className="text-lg font-bold text-stone-900 font-display">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1 rounded-md text-stone-500 hover:text-stone-700 hover:bg-stone-100 transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * Confirmation for something irreversible.
 *
 * Project and user deletion used a two-click trash icon that turned into a
 * "Confirm" button *in the same position*, so a double-click permanently deleted
 * a project and all its keyword history with no dialog and no statement of what
 * was lost. This exists so those paths can say what they destroy, the way the
 * keyword and backlink screens already do.
 */
export function ConfirmModal({ title, onCancel, onConfirm, confirmLabel = "Delete", busy, confirmDisabled, children }) {
  return (
    <Modal title={title} onClose={onCancel} dismissOnBackdrop={!busy}>
      <div className="text-sm text-stone-600">{children}</div>
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onCancel} disabled={busy} className={`${BTN_GHOST} px-4 py-2`}>
          Cancel
        </button>
        <button
          onClick={onConfirm}
          // confirmDisabled is for a caller that gates on something of its own
          // — an "I understand" tick, say — where a spinner would be a lie.
          disabled={busy || confirmDisabled}
          className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:opacity-60"
        >
          {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Trash2 size={15} />}
          {confirmLabel}
        </button>
      </div>
    </Modal>
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

export function ChangePasswordModal({ onClose }) {
  const [otpRequired, setOtpRequired] = useState(null);
  const [phase, setPhase] = useState("request");
  const [emailSentTo, setEmailSentTo] = useState(null);
  const [code, setCode] = useState("");
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/auth/config")
      .then((d) => setOtpRequired(!!d.passwordOtpRequired))
      .catch(() => setOtpRequired(true));
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
      const d = await api("/auth/password/change", { method: "POST", body });
      // The change signs out every other session by bumping the account's token
      // version; this replacement keeps the current one alive. Without storing
      // it, the next request 401s and the user is bounced to the login screen
      // immediately after successfully changing their password.
      if (d?.token) setToken(d.token);
      setPhase("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const passwordFields = (
    <>
      <label htmlFor="pw-new" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">New password</label>
      <input
        id="pw-new"
        type="password"
          autoComplete="new-password"
        value={pw1}
        onChange={(e) => setPw1(e.target.value)}
        placeholder="At least 8 characters"
        autoFocus
        className={`${INPUT_CLS} mb-4`}
      />
      <label htmlFor="pw-confirm" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Confirm new password</label>
      <input
        id="pw-confirm"
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
          <label htmlFor="pw-otp" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Code</label>
          <input
            id="pw-otp"
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
