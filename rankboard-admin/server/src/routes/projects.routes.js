/* ════════════════════════════════════════════════════════════════════
   PROJECT ROUTES — the main website's API.

   Viewing is open to every signed-in user (provisional — client
   scoping comes later). Every mutation is gated by the permission
   matrix via requirePermission, so when you change a role's rules
   in permissions.js, the API enforcement changes with it.
   ════════════════════════════════════════════════════════════════════ */
import { Router } from "express";
import db from "../db.js";
import { requireAuth } from "../middleware/auth.js";
import { requirePermission } from "../permissions.js";

const router = Router();
router.use(requireAuth);

const rowToProject = (p) => ({
  id: p.id,
  name: p.name,
  active: !!p.active,
  createdAt: p.created_at,
  ...(p.keyword_count !== undefined ? { keywordCount: p.keyword_count } : {}),
});

const rowToKeyword = (k) => ({
  id: k.id,
  term: k.term,
  currentRank: k.current_rank,
  previousRank: k.previous_rank, // null = first lookup ("New")
  lastChecked: k.last_checked,
});

/* GET /api/projects — every project plus how many keywords it tracks.
   The LEFT JOIN + GROUP BY is your first real SQL move beyond
   SELECT *: LEFT (not INNER) so projects with zero keywords still
   appear; COUNT(k.id) counts only matching keyword rows. */
router.get("/", (req, res) => {
  const rows = db
    .prepare(
      `SELECT p.*, COUNT(k.id) AS keyword_count
       FROM projects p
       LEFT JOIN keywords k ON k.project_id = p.id
       GROUP BY p.id
       ORDER BY p.created_at DESC, p.id DESC`
    )
    .all();
  res.json({ projects: rows.map(rowToProject) });
});

/* GET /api/projects/:id — one project with its full keyword list. */
router.get("/:id", (req, res) => {
  const project = db.prepare("SELECT * FROM projects WHERE id = ?").get(req.params.id);
  if (!project) return res.status(404).json({ error: "Project not found." });

  const keywords = db
    .prepare("SELECT * FROM keywords WHERE project_id = ? ORDER BY created_at, id")
    .all(project.id);

  res.json({ project: { ...rowToProject(project), keywords: keywords.map(rowToKeyword) } });
});

/* POST /api/projects — create. */
router.post("/", requirePermission("addProject"), (req, res) => {
  const { name } = req.body || {};
  if (!name?.trim()) return res.status(400).json({ error: "Project name is required." });

  const info = db.prepare("INSERT INTO projects (name, active) VALUES (?, 1)").run(name.trim());
  const project = db.prepare("SELECT * FROM projects WHERE id = ?").get(info.lastInsertRowid);
  res.status(201).json({ project: rowToProject(project) });
});

/* PATCH /api/projects/:id — the active/inactive toggle. */
router.patch("/:id", requirePermission("toggleProject"), (req, res) => {
  const { active } = req.body || {};
  if (typeof active !== "boolean") return res.status(400).json({ error: "Send { active: true|false }." });

  const info = db.prepare("UPDATE projects SET active = ? WHERE id = ?").run(active ? 1 : 0, req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "Project not found." });
  res.json({ ok: true });
});

/* DELETE /api/projects/:id — the FK cascade in the schema deletes the
   project's keywords automatically. No manual cleanup, no orphans. */
router.delete("/:id", requirePermission("deleteProject"), (req, res) => {
  const info = db.prepare("DELETE FROM projects WHERE id = ?").run(req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "Project not found." });
  res.json({ ok: true });
});

/* POST /api/projects/:id/keywords — add a keyword to the ledger. */
router.post("/:id/keywords", requirePermission("addKeyword"), (req, res) => {
  const project = db.prepare("SELECT id FROM projects WHERE id = ?").get(req.params.id);
  if (!project) return res.status(404).json({ error: "Project not found." });

  const { term, currentRank, previousRank } = req.body || {};
  const cur = Number(currentRank);
  const prev = previousRank == null || previousRank === "" ? null : Number(previousRank);

  if (!term?.trim()) return res.status(400).json({ error: "Keyword is required." });
  if (!Number.isInteger(cur) || cur < 1) return res.status(400).json({ error: "Current rank must be a whole number of 1 or more." });
  if (prev !== null && (!Number.isInteger(prev) || prev < 1)) return res.status(400).json({ error: "Previous rank must be a whole number of 1 or more." });

  const info = db
    .prepare("INSERT INTO keywords (project_id, term, current_rank, previous_rank) VALUES (?, ?, ?, ?)")
    .run(project.id, term.trim().toLowerCase(), cur, prev);

  const keyword = db.prepare("SELECT * FROM keywords WHERE id = ?").get(info.lastInsertRowid);
  res.status(201).json({ keyword: rowToKeyword(keyword) });
});

/* PATCH /api/projects/:id/keywords/:kwId — record a NEW LOOKUP.
   This is the heart of the ledger's time semantics: the rank that was
   "current" becomes "previous", the new number becomes "current", and
   last_checked is stamped. A future automated rank-checker (cron job
   + rank API) will call this exact same write path — the only thing
   that changes is WHO supplies the number. */
router.patch("/:id/keywords/:kwId", requirePermission("addKeyword"), (req, res) => {
  const rank = Number(req.body?.newRank);
  if (!Number.isInteger(rank) || rank < 1) {
    return res.status(400).json({ error: "New rank must be a whole number of 1 or more." });
  }

  const kw = db
    .prepare("SELECT * FROM keywords WHERE id = ? AND project_id = ?")
    .get(req.params.kwId, req.params.id);
  if (!kw) return res.status(404).json({ error: "Keyword not found." });

  db.prepare(
    `UPDATE keywords
     SET previous_rank = current_rank, current_rank = ?, last_checked = date('now')
     WHERE id = ?`
  ).run(rank, kw.id);

  const updated = db.prepare("SELECT * FROM keywords WHERE id = ?").get(kw.id);
  res.json({ keyword: rowToKeyword(updated) });
});

/* DELETE /api/projects/:id/keywords/:kwId — remove from the ledger.
   The WHERE clause checks BOTH ids so a keyword can only be deleted
   through its own project — a small habit that matters a lot once
   per-project access rules exist. */
router.delete("/:id/keywords/:kwId", requirePermission("deleteKeyword"), (req, res) => {
  const info = db
    .prepare("DELETE FROM keywords WHERE id = ? AND project_id = ?")
    .run(req.params.kwId, req.params.id);
  if (info.changes === 0) return res.status(404).json({ error: "Keyword not found." });
  res.json({ ok: true });
});

export default router;
