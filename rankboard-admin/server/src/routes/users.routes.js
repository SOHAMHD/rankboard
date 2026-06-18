/* ════════════════════════════════════════════════════════════════════
   USER ROUTES — the admin panel's API. Every route in this file is
   gated twice at the top: requireAuth (valid token) then
   requireRole('Super Admin'). A Team member with devtools open can
   POST here all day; the server answers 403 every time.
   ════════════════════════════════════════════════════════════════════ */
import { Router } from "express";
import bcrypt from "bcryptjs";
import crypto from "node:crypto";
import db from "../db.js";
import { requireAuth } from "../middleware/auth.js";
import { requirePermission } from "../permissions.js";
import { sendInviteEmail } from "../services/email.service.js";

const router = Router();
router.use(requireAuth, requirePermission("manageUsers"));

const ROLES = ["Super Admin", "Admin", "Team", "Client"];
const isValidEmail = (e) => /\S+@\S+\.\S+/.test(e);

/* Temp passwords skip lookalike characters (0/O, 1/l/I) — people
   type these from an email. crypto.randomInt is cryptographically
   random, unlike Math.random which is guessable. */
function generateTempPassword() {
  const chars = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";
  let pw = "";
  for (let i = 0; i < 10; i++) pw += chars[crypto.randomInt(chars.length)];
  return pw;
}

const rowToUser = (u) => ({
  id: u.id,
  name: u.name,
  email: u.email,
  role: u.role,
  status: u.status,
  createdAt: u.created_at,
});

/* GET /api/users — list everyone (no password hashes, ever). */
router.get("/", (req, res) => {
  const rows = db
    .prepare("SELECT id, name, email, role, status, created_at FROM users ORDER BY created_at, id")
    .all();
  res.json({ users: rows.map(rowToUser) });
});

/* POST /api/users — onboard someone.
   Creates the account with a hashed temp password and "sends" the
   invite email. The response includes the email so the UI can show
   it — this is the ONLY time the temp password leaves the server in
   plain text, because after hashing it cannot be read back. */
router.post("/", async (req, res) => {
  const { name, email, role } = req.body || {};

  if (!name?.trim()) return res.status(400).json({ error: "Name is required." });
  if (!isValidEmail(email || "")) return res.status(400).json({ error: "A valid email is required." });
  if (!ROLES.includes(role)) return res.status(400).json({ error: "Unknown role." });

  const cleanEmail = email.trim().toLowerCase();
  const tempPassword = generateTempPassword();

  let info;
  try {
    info = db
      .prepare(
        `INSERT INTO users (name, email, role, password_hash, must_change_password, status)
         VALUES (?, ?, ?, ?, 1, 'invited')`
      )
      .run(name.trim(), cleanEmail, role, bcrypt.hashSync(tempPassword, 10));
  } catch (err) {
    // The UNIQUE constraint on email throws here — the DB is the
    // final guard against duplicates, even under race conditions.
    if (String(err.message).includes("UNIQUE")) {
      return res.status(409).json({ error: "Someone with this email already exists." });
    }
    throw err;
  }

  const emailRecord = await sendInviteEmail({ name: name.trim(), email: cleanEmail, role, tempPassword });
  const user = db
    .prepare("SELECT id, name, email, role, status, created_at FROM users WHERE id = ?")
    .get(info.lastInsertRowid);

  res.status(201).json({ user: rowToUser(user), email: emailRecord });
});

/* POST /api/users/:id/resend-invite
   We can't re-show the old temp password — only its hash exists.
   So "resend" means: generate a NEW temp password, overwrite the
   hash, send a fresh email. This is exactly how real systems work. */
router.post("/:id/resend-invite", async (req, res) => {
  const user = db.prepare("SELECT * FROM users WHERE id = ?").get(req.params.id);
  if (!user) return res.status(404).json({ error: "User not found." });
  if (user.status !== "invited") {
    return res.status(400).json({ error: "This person has already activated their account." });
  }

  const tempPassword = generateTempPassword();
  db.prepare("UPDATE users SET password_hash = ? WHERE id = ?").run(
    bcrypt.hashSync(tempPassword, 10),
    user.id
  );

  const emailRecord = await sendInviteEmail({ name: user.name, email: user.email, role: user.role, tempPassword });
  res.json({ email: emailRecord });
});

/* PATCH /api/users/:id — change someone's role.
   The self-guard lives HERE, on the server. The UI disables the
   control too, but that's courtesy; this line is the law. */
router.patch("/:id", (req, res) => {
  const { role } = req.body || {};
  if (!ROLES.includes(role)) return res.status(400).json({ error: "Unknown role." });
  if (Number(req.params.id) === req.user.id) {
    return res.status(400).json({ error: "You can't change your own role." });
  }

  const info = db.prepare("UPDATE users SET role = ? WHERE id = ?").run(role, req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "User not found." });
  res.json({ ok: true });
});

/* DELETE /api/users/:id — remove someone (never yourself). */
router.delete("/:id", (req, res) => {
  if (Number(req.params.id) === req.user.id) {
    return res.status(400).json({ error: "You can't remove yourself." });
  }
  const info = db.prepare("DELETE FROM users WHERE id = ?").run(req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "User not found." });
  res.json({ ok: true });
});

export default router;
