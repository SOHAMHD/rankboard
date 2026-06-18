/* ════════════════════════════════════════════════════════════════════
   PERMISSIONS — the single source of truth, now living on the SERVER.

   In the browser prototype this matrix could be edited in devtools.
   Here it cannot: the client only receives a copy (via /api/auth/me)
   to know which buttons to draw. Enforcement happens in
   requirePermission below, on every request.

   ← provisional rows: Team and Client rules are placeholders until
   they're decided. Flip booleans here and BOTH the API enforcement
   and the UI (which renders what the server sends) follow.
   ════════════════════════════════════════════════════════════════════ */

export const PERMISSIONS = {
  //                manageUsers  addProject  toggleProject  deleteProject  addKeyword  deleteKeyword
  "Super Admin": { manageUsers: true,  addProject: true,  toggleProject: true,  deleteProject: true,  addKeyword: true,  deleteKeyword: true  },
  "Admin":       { manageUsers: false, addProject: true,  toggleProject: true,  deleteProject: true,  addKeyword: true,  deleteKeyword: true  }, // a.k.a. Manager
  "Team":        { manageUsers: false, addProject: false, toggleProject: false, deleteProject: false, addKeyword: true,  deleteKeyword: true  }, // ← provisional
  "Client":      { manageUsers: false, addProject: false, toggleProject: false, deleteProject: false, addKeyword: false, deleteKeyword: false }, // ← provisional: read-only
};

// Default-deny: unknown role or unknown action → false.
export const can = (user, action) => PERMISSIONS[user?.role]?.[action] ?? false;

/* Drop-in route guard:  router.post("/", requirePermission("addProject"), ...) */
export const requirePermission = (action) => (req, res, next) =>
  can(req.user, action)
    ? next()
    : res.status(403).json({ error: "You don't have permission to do that." });
