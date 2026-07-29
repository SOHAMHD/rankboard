/* ════════════════════════════════════════════════════════════════════
   AUTH SCREENS — sign in, and the forced first-time password change.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";
import { KeyRound, LoaderCircle, Lock, Mail, ShieldCheck } from "lucide-react";
import { api, setToken } from "../api";
import { DarkShell, ErrorNote, INPUT_CLS, BTN_PRIMARY } from "../ui";

export function LoginView({ onLogin }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [forgot, setForgot] = useState(false);

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

  if (forgot) {
    return <ForgotPasswordView initialEmail={email} onBack={() => setForgot(false)} />;
  }

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
        <button
          onClick={() => { setError(null); setForgot(true); }}
          className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors"
        >
          Forgot password?
        </button>
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

/* ════════════════════════════════════════════════════════════════════
   TWO-STEP VERIFICATION — the authenticator step after the password.
   Enrollment (first time): scan the QR / enter the key, confirm a code,
   save one-time backup codes. Returning: enter the current code (or a
   backup code). On success the parent swaps the pending token for the
   verified one via onVerified(token, user).
   ════════════════════════════════════════════════════════════════════ */
export function TwoFactorView({ user, enrolled, onVerified, onLogout }) {
  const [mode, setMode] = useState(enrolled ? "verify" : "enroll"); // enroll | verify | backup | codes
  const [setup, setSetup] = useState(null); // { secret, otpauthUri }
  const [qr, setQr] = useState(null); // QR image data URL
  const [code, setCode] = useState("");
  const [backupCodes, setBackupCodes] = useState(null);
  const [pending, setPending] = useState(null); // { token, user, stage, emailSentTo } after enroll
  const [emailSentTo, setEmailSentTo] = useState(null); // masked address for the email step
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  // Begin enrollment once: fetch a provisional secret and render its QR here
  // in the browser (the secret never touches a third-party QR service).
  useEffect(() => {
    if (enrolled || started.current) return;
    started.current = true;
    api("/auth/2fa/enroll", { method: "POST" })
      .then(async (d) => {
        setSetup(d);
        try {
          setQr(await QRCode.toDataURL(d.otpauthUri, { margin: 1, width: 208 }));
        } catch {
          setQr(null); // fall back to the manual key
        }
      })
      .catch((err) => setError(err.message));
  }, [enrolled]);

  // Route a verify/enroll response: an admin gets an email step (stage
  // "email") — stash the intermediate token so the next call is authed — while
  // everyone else is done.
  const goNext = (d) => {
    if (d.stage === "email") {
      setToken(d.token);
      setEmailSentTo(d.emailSentTo);
      setCode("");
      setError(null);
      setMode("email");
    } else {
      onVerified(d.token, d.user);
    }
  };

  const finishFromCodes = () => {
    if (pending.stage === "email") {
      setToken(pending.token);
      setEmailSentTo(pending.emailSentTo);
      setCode("");
      setMode("email");
    } else {
      onVerified(pending.token, pending.user);
    }
  };

  const verifyEmail = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api("/auth/2fa/verify-email", { method: "POST", body: { code: code.trim() } });
      onVerified(d.token, d.user);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const resendEmail = async () => {
    setError(null);
    try {
      const d = await api("/auth/2fa/resend-email", { method: "POST" });
      setEmailSentTo(d.emailSentTo);
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmEnroll = async () => {
    setBusy(true);
    setError(null);
    try {
      const d = await api("/auth/2fa/enroll/confirm", { method: "POST", body: { code: code.trim() } });
      setBackupCodes(d.backupCodes);
      setPending({ token: d.token, user: d.user, stage: d.stage, emailSentTo: d.emailSentTo });
      setMode("codes");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const verify = async () => {
    setBusy(true);
    setError(null);
    try {
      const path = mode === "backup" ? "/auth/2fa/verify-backup" : "/auth/2fa/verify";
      const d = await api(path, { method: "POST", body: { code: code.trim() } });
      goNext(d);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (mode === "codes") {
    return (
      <DarkShell>
        <div className="bg-white rounded-2xl shadow-2xl p-7">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck size={18} className="text-emerald-600" />
            <h1 className="text-xl font-bold text-stone-900 font-display">Save your backup codes</h1>
          </div>
          <p className="text-sm text-stone-500 mt-1 mb-4">
            Each code works once. Keep them somewhere safe — they're the only way in if you lose your
            phone, and you won't see them again.
          </p>
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-stone-200 bg-stone-50 p-3 font-data text-sm text-stone-800">
            {(backupCodes || []).map((c) => (
              <span key={c} className="tracking-widest">{c}</span>
            ))}
          </div>
          <button onClick={finishFromCodes} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            I've saved these — continue
          </button>
        </div>
      </DarkShell>
    );
  }

  if (mode === "enroll") {
    return (
      <DarkShell>
        <div className="bg-white rounded-2xl shadow-2xl p-7">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck size={18} className="text-orange-600" />
            <h1 className="text-xl font-bold text-stone-900 font-display">Set up two-step verification</h1>
          </div>
          <p className="text-sm text-stone-500 mt-1 mb-4">
            Scan this with Google Authenticator (or any authenticator app), then enter the 6-digit code it shows.
          </p>
          <div className="flex flex-col items-center gap-3 mb-4">
            {qr ? (
              <img src={qr} alt="Authenticator QR code" className="rounded-lg border border-stone-200" width={208} height={208} />
            ) : (
              <div className="h-52 w-52 flex items-center justify-center text-stone-400">
                <LoaderCircle size={22} className="animate-spin" />
              </div>
            )}
            {setup && (
              <p className="text-xs text-stone-400 text-center">
                Can't scan? Enter this key manually:
                <br />
                <span className="font-data text-stone-600 tracking-wider break-all">{setup.secret}</span>
              </p>
            )}
          </div>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && code.length === 6 && confirmEnroll()}
            placeholder="123456"
            className={`${INPUT_CLS} text-center tracking-[0.5em] font-data`}
          />
          <ErrorNote>{error}</ErrorNote>
          <button onClick={confirmEnroll} disabled={code.length !== 6 || busy || !setup} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Verify and turn on"}
          </button>
          <button onClick={onLogout} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
            Sign out instead
          </button>
        </div>
      </DarkShell>
    );
  }

  if (mode === "email") {
    return (
      <DarkShell>
        <div className="bg-white rounded-2xl shadow-2xl p-7">
          <div className="flex items-center gap-2 mb-1">
            <Mail size={18} className="text-orange-600" />
            <h1 className="text-xl font-bold text-stone-900 font-display">Check your email</h1>
          </div>
          <p className="text-sm text-stone-500 mt-1 mb-5">
            We sent a 6-digit code to {emailSentTo || "your email"}. Enter it to finish signing in.
          </p>
          <input
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            onKeyDown={(e) => e.key === "Enter" && code.length === 6 && verifyEmail()}
            placeholder="123456"
            autoFocus
            className={`${INPUT_CLS} text-center tracking-[0.5em] font-data`}
          />
          <ErrorNote>{error}</ErrorNote>
          <button onClick={verifyEmail} disabled={code.length !== 6 || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Verify"}
          </button>
          <button onClick={resendEmail} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
            Resend code
          </button>
          <button onClick={onLogout} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-2 transition-colors">
            Sign out
          </button>
        </div>
      </DarkShell>
    );
  }

  const backup = mode === "backup";
  return (
    <DarkShell>
      <div className="bg-white rounded-2xl shadow-2xl p-7">
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={18} className="text-orange-600" />
          <h1 className="text-xl font-bold text-stone-900 font-display">Two-step verification</h1>
        </div>
        <p className="text-sm text-stone-500 mt-1 mb-5">
          {backup
            ? "Enter one of your backup codes."
            : `Enter the 6-digit code from your authenticator app, ${user.name.split(" ")[0]}.`}
        </p>
        <input
          type="text"
          inputMode={backup ? "text" : "numeric"}
          autoComplete="one-time-code"
          value={code}
          onChange={(e) => setCode(backup ? e.target.value.toUpperCase() : e.target.value.replace(/\D/g, "").slice(0, 6))}
          onKeyDown={(e) => e.key === "Enter" && verify()}
          placeholder={backup ? "ABCD-EFGH" : "123456"}
          autoFocus
          className={`${INPUT_CLS} text-center tracking-[0.4em] font-data`}
        />
        <ErrorNote>{error}</ErrorNote>
        <button onClick={verify} disabled={busy || !code} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
          {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Verify"}
        </button>
        <button
          onClick={() => { setError(null); setCode(""); setMode(backup ? "verify" : "backup"); }}
          className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors"
        >
          {backup ? "Use authenticator code instead" : "Use a backup code"}
        </button>
        <button onClick={onLogout} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-2 transition-colors">
          Sign out
        </button>
      </div>
    </DarkShell>
  );
}


/* ════════════════════════════════════════════════════════════════════
   FORGOT PASSWORD — pre-login reset. Enter your email → we email a
   one-time code → enter the code + a new password. The server never
   reveals whether an email exists.
   ════════════════════════════════════════════════════════════════════ */
export function ForgotPasswordView({ initialEmail = "", onBack }) {
  const [phase, setPhase] = useState("email"); // email | reset | done
  const [email, setEmail] = useState(initialEmail);
  const [code, setCode] = useState("");
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const requestCode = async () => {
    if (!/\S+@\S+\.\S+/.test(email.trim())) return setError("Enter a valid email address.");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/forgot-password/request", { method: "POST", body: { email: email.trim() } });
      setPhase("reset");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const reset = async () => {
    if (pw1.length < 8) return setError("Password needs at least 8 characters.");
    if (pw1 !== pw2) return setError("The two passwords don't match.");
    setBusy(true);
    setError(null);
    try {
      await api("/auth/forgot-password/reset", {
        method: "POST",
        body: { email: email.trim(), code: code.trim(), newPassword: pw1 },
      });
      setPhase("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <DarkShell>
      <div className="bg-white rounded-2xl shadow-2xl p-7">
        <div className="flex items-center gap-2 mb-1">
          <KeyRound size={18} className="text-orange-600" />
          <h1 className="text-xl font-bold text-stone-900 font-display">Reset password</h1>
        </div>

        {phase === "email" && (
          <>
            <p className="text-sm text-stone-500 mt-1 mb-5">
              Enter your account email and we'll send you a one-time reset code.
            </p>
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && requestCode()}
              placeholder="you@company.com"
              autoFocus
              className={INPUT_CLS}
            />
            <ErrorNote>{error}</ErrorNote>
            <button onClick={requestCode} disabled={busy || !email} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
              {busy ? <LoaderCircle size={16} className="animate-spin" /> : (<><Mail size={15} /> Send reset code</>)}
            </button>
            <button onClick={onBack} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
              Back to sign in
            </button>
          </>
        )}

        {phase === "reset" && (
          <>
            <p className="text-sm text-stone-500 mt-1 mb-5">
              If an account exists for {email}, we've sent a 6-digit code. Enter it and choose a new password.
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
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">New password</label>
            <input
              type="password"
              value={pw1}
              onChange={(e) => setPw1(e.target.value)}
              placeholder="At least 8 characters"
              className={`${INPUT_CLS} mb-4`}
            />
            <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Confirm new password</label>
            <input
              type="password"
              value={pw2}
              onChange={(e) => setPw2(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && reset()}
              placeholder="Same again"
              className={INPUT_CLS}
            />
            <ErrorNote>{error}</ErrorNote>
            <button onClick={reset} disabled={busy || !code || !pw1 || !pw2} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
              {busy ? <LoaderCircle size={16} className="animate-spin" /> : "Reset password"}
            </button>
            <button onClick={requestCode} disabled={busy} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-3 transition-colors">
              Resend code
            </button>
            <button onClick={onBack} className="w-full text-xs text-stone-400 hover:text-stone-600 mt-2 transition-colors">
              Back to sign in
            </button>
          </>
        )}

        {phase === "done" && (
          <>
            <p className="text-sm text-stone-600 mt-1 mb-5">
              Your password has been reset. Sign in with your new password.
            </p>
            <button onClick={onBack} className={`${BTN_PRIMARY} w-full py-2.5`}>Back to sign in</button>
          </>
        )}
      </div>
    </DarkShell>
  );
}
