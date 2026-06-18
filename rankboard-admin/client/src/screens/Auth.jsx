/* ════════════════════════════════════════════════════════════════════
   AUTH SCREENS — sign in, and the forced first-time password change.
   ════════════════════════════════════════════════════════════════════ */
import { useState } from "react";
import { LoaderCircle, Lock } from "lucide-react";
import { api } from "../api";
import { DarkShell, ErrorNote, INPUT_CLS, BTN_PRIMARY } from "../ui";

export function LoginView({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await onLogin(email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <DarkShell>
      <div className="bg-white rounded-2xl shadow-2xl p-7">
        <h1 className="text-xl font-bold text-stone-900 font-display">Sign in</h1>
        <p className="text-sm text-stone-500 mt-1 mb-5">Use the credentials from your invite email.</p>

        <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Email</label>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          autoFocus
          className={`${INPUT_CLS} mb-4`}
        />

        <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="••••••••"
          className={INPUT_CLS}
        />

        <ErrorNote>{error}</ErrorNote>

        <button onClick={submit} disabled={!email || !password || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
          {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Sign in"}
        </button>

        <div className="mt-5 pt-4 border-t border-stone-100">
          <p className="text-xs text-stone-400 text-center">
            First run seeds a Super Admin: <span className="font-data text-stone-600">soham@infyappdevelopment.com</span> /{" "}
            <span className="font-data text-stone-600">admin123</span>
          </p>
        </div>
      </div>
    </DarkShell>
  );
}

export function SetPasswordView({ user, onDone, onLogout }) {
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (pw1.length < 8) return setError("Password needs at least 8 characters.");
    if (pw1 !== pw2) return setError("The two passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/set-password", { method: "POST", body: { newPassword: pw1 } });
      await onDone();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <DarkShell>
      <div className="bg-white rounded-2xl shadow-2xl p-7">
        <div className="flex items-center gap-2 mb-1">
          <Lock size={18} className="text-orange-600" />
          <h1 className="text-xl font-bold text-stone-900 font-display">Set your password</h1>
        </div>
        <p className="text-sm text-stone-500 mt-1 mb-5">
          Welcome, {user.name.split(" ")[0]}. Your temporary password worked — now replace it with one only you know.
        </p>

        <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
          New password
        </label>
        <input
          type="password"
          value={pw1}
          onChange={(e) => setPw1(e.target.value)}
          placeholder="At least 8 characters"
          autoFocus
          className={`${INPUT_CLS} mb-4`}
        />

        <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
          Confirm password
        </label>
        <input
          type="password"
          value={pw2}
          onChange={(e) => setPw2(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Same again"
          className={INPUT_CLS}
        />

        <ErrorNote>{error}</ErrorNote>

        <button onClick={submit} disabled={!pw1 || !pw2 || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
          {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Save and continue"}
        </button>

        <button onClick={onLogout} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
          Sign out instead
        </button>
      </div>
    </DarkShell>
  );
}
