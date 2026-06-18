/* ════════════════════════════════════════════════════════════════════
   SHARED UI — design tokens and components every screen uses.

   Why split files now: one giant App.jsx was fine for a prototype,
   but each screen growing independently makes a single file painful
   to navigate and review. The rule of thumb: split when a file has
   more than one reason to change.
   ════════════════════════════════════════════════════════════════════ */
import { BarChart3, LogOut, Users, X } from "lucide-react";

export const ROLES = ["Super Admin", "Admin", "Team", "Client"];

export const ROLE_DESCRIPTIONS = {
  "Super Admin": "Full control. Onboards people and assigns roles.",
  "Admin": "Also called Manager. Permissions to be decided.",
  "Team": "Permissions to be decided.",
  "Client": "Permissions to be decided — most likely read-only.",
};

export const ROLE_STYLES = {
  "Super Admin": "bg-violet-100 text-violet-700",
  "Admin": "bg-sky-100 text-sky-700",
  "Team": "bg-teal-100 text-teal-700",
  "Client": "bg-stone-200 text-stone-600",
};

export const INPUT_CLS =
  "w-full rounded-lg border border-stone-300 px-3 py-2 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-colors";

export const BTN_PRIMARY =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-orange-600 hover:bg-orange-700 text-white text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2 disabled:opacity-40 disabled:cursor-not-allowed";

export const BTN_GHOST =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-stone-300 hover:border-stone-400 bg-white text-stone-700 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500";

/* The client-side `can` reads the permissions object the SERVER sent
   with the user (from /api/auth/me). The matrix itself lives in one
   place — server/src/permissions.js — and the client just renders
   what it's told. Hiding a button here is UX; the API re-checks. */
export const can = (user, action) => !!user?.permissions?.[action];

export function TopBar({ user, onLogout, onPeople, onHome }) {
  return (
    <header className="bg-white border-b border-stone-200 sticky top-0 z-10">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <button onClick={onHome} className="flex items-center gap-2" aria-label="Go to projects">
          <span className="h-7 w-7 rounded-lg bg-orange-600 flex items-center justify-center">
            <BarChart3 size={14} className="text-white" />
          </span>
          <span className="font-bold text-stone-900 font-display">RankBoard</span>
        </button>
        <div className="flex items-center gap-2 sm:gap-3">
          {onPeople && can(user, "manageUsers") && (
            <button
              onClick={onPeople}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-stone-600 hover:text-stone-900 px-2.5 py-1.5 rounded-lg hover:bg-stone-100 transition-colors"
            >
              <Users size={15} /> <span className="hidden sm:inline">People</span>
            </button>
          )}
          <span className="text-sm text-stone-600 hidden sm:inline">{user.name}</span>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${ROLE_STYLES[user.role]}`}>{user.role}</span>
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
      style={{ background: "radial-gradient(70% 55% at 50% 0%, rgba(234,88,12,0.18), transparent 70%), #0f172a" }}
    >
      <div className="w-full max-w-sm">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="h-10 w-10 rounded-xl bg-orange-600 flex items-center justify-center shadow-lg">
            <BarChart3 size={20} className="text-white" />
          </div>
          <div>
            <p className="text-white font-semibold text-lg leading-tight font-display">RankBoard</p>
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
        on ? "bg-emerald-500" : "bg-stone-300"
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
