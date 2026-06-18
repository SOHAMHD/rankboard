/* ════════════════════════════════════════════════════════════════════
   AUTH ROUTES — login, session check, first-time password change.
   ════════════════════════════════════════════════════════════════════ */
import { Router } from "express";
import bcrypt from "bcryptjs";
import jwt from "jsonwebtoken";
import db from "../db.js";
import { JWT_SECRET } from "../config.js";
import { requireAuth } from "../middleware/auth.js";
import { PERMISSIONS } from "../permissions.js";

const router = Router();

/* Shape we expose to the client. NEVER includes password_hash —
   what the API doesn't return can't leak. */
const publicUser = (u) => ({
  id: u.id,
  name: u.name,
  email: u.email,
  role: u.role,
  status: u.status,
  mustChangePassword: !!u.must_change_password,
  permissions: PERMISSIONS[u.role] ?? {}, // the client renders buttons from this; the server still re-checks every request
});

/* POST /api/auth/login
   The `?` placeholder is a parameterized query: the email value is
   passed as DATA, never glued into the SQL string. This is the
   defense against SQL injection — even an email like
   "' OR 1=1 --" is just a weird string that matches nothing. */
router.post("/login", (req, res) => {
  const { email, password } = req.body || {};
  if (!email || !password) {
    return res.status(400).json({ error: "Email and password are required." });
  }

  const user = db
    .prepare("SELECT * FROM users WHERE email = ?")
    .get(String(email).trim().toLowerCase());

  // Same generic message whether the email or the password is wrong —
  // a specific "wrong password" would confirm the account exists,
  // letting outsiders harvest valid emails (account enumeration).
  if (!user || !bcrypt.compareSync(password, user.password_hash)) {
    return res.status(401).json({ error: "No account matches that email and password." });
  }

  // The token contains only the user's id (sub = "subject") and an
  // expiry. The signature makes it tamper-proof: change one character
  // and verification fails.
  const token = jwt.sign({ sub: user.id }, JWT_SECRET, { expiresIn: "8h" });
  res.json({ token, user: publicUser(user) });
});

/* GET /api/auth/me — "who am I?"
   Called on page load so a refresh doesn't log the user out. */
router.get("/me", requireAuth, (req, res) => {
  res.json({ user: publicUser(req.user) });
});

/* POST /api/auth/set-password
   Completes onboarding: replaces the temporary password and flips
   the lifecycle from 'invited' to 'active'. Once hashed, the old
   password is gone for good — not even the server can recover it. */
router.post("/set-password", requireAuth, (req, res) => {
  const { newPassword } = req.body || {};
  if (!newPassword || newPassword.length < 8) {
    return res.status(400).json({ error: "Password needs at least 8 characters." });
  }

  db.prepare(
    `UPDATE users
     SET password_hash = ?, must_change_password = 0, status = 'active'
     WHERE id = ?`
  ).run(bcrypt.hashSync(newPassword, 10), req.user.id);

  res.json({ ok: true });
});

export default router;
