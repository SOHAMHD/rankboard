/* ════════════════════════════════════════════════════════════════════
   AUTH MIDDLEWARE — this is where permissions become REAL.

   In the browser prototype, hiding a button was the only "security".
   Here, every protected request must carry a valid token, and the
   server decides — a user can craft any request they like with curl
   or devtools, and these two functions still say no.
   ════════════════════════════════════════════════════════════════════ */
import jwt from "jsonwebtoken";
import db from "../db.js";
import { JWT_SECRET } from "../config.js";

/* requireAuth: proves WHO is calling.
   The client sends "Authorization: Bearer <token>". The token is a
   JWT we signed at login — if anyone tampers with it, the signature
   check fails. We then load the user fresh from the DB rather than
   trusting data inside the token: if their role changed or their
   account was deleted five minutes ago, that applies immediately. */
export function requireAuth(req, res, next) {
  const header = req.headers.authorization || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: "Sign in required." });

  let payload;
  try {
    payload = jwt.verify(token, JWT_SECRET);
  } catch {
    return res.status(401).json({ error: "Session expired. Please sign in again." });
  }

  const user = db
    .prepare(
      "SELECT id, name, email, role, must_change_password, status FROM users WHERE id = ?"
    )
    .get(payload.sub);
  if (!user) return res.status(401).json({ error: "This account no longer exists." });

  req.user = user; // downstream handlers can rely on this
  next();
}

/* requireRole: proves the caller is ALLOWED.
   401 = "we don't know who you are", 403 = "we know exactly who you
   are, and the answer is no". Using the right status code matters —
   clients react differently to each. */
export function requireRole(...roles) {
  return (req, res, next) => {
    if (!roles.includes(req.user.role)) {
      return res.status(403).json({ error: "You don't have permission to do that." });
    }
    next();
  };
}
