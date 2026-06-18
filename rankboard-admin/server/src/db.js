/* ════════════════════════════════════════════════════════════════════
   DATABASE LAYER — SQLite via node:sqlite (built into Node 22.13+).
   ════════════════════════════════════════════════════════════════════ */
import { DatabaseSync } from "node:sqlite";
import bcrypt from "bcryptjs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const db = new DatabaseSync(path.join(__dirname, "..", "rankboard.db"));

db.exec("PRAGMA journal_mode = WAL;");
/* GOTCHA worth knowing: SQLite ships with foreign keys turned OFF for
   historical reasons. Without this pragma, ON DELETE CASCADE below
   would silently do nothing. */
db.exec("PRAGMA foreign_keys = ON;");

/* ---- Schema ----
   users     — accounts + roles (the admin panel)
   emails    — invite outbox
   projects  — one row per website/client you do SEO for
   keywords  — many rows per project (one-to-many). The FOREIGN KEY
               with ON DELETE CASCADE means deleting a project takes
               its keywords with it — relational integrity enforced
               by the database, not by remembering to clean up. */
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    name                 TEXT NOT NULL,
    email                TEXT NOT NULL UNIQUE,
    role                 TEXT NOT NULL CHECK (role IN ('Super Admin','Admin','Team','Client')),
    password_hash        TEXT NOT NULL,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','active')),
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS emails (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    to_email TEXT NOT NULL,
    subject  TEXT NOT NULL,
    body     TEXT NOT NULL,
    sent_at  TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS projects (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS keywords (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    term          TEXT NOT NULL,
    current_rank  INTEGER  CHECK (current_rank >= 1),
    previous_rank INTEGER CHECK (previous_rank >= 1),
    last_checked  TEXT NOT NULL DEFAULT (date('now')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
  );
`);

/* ---- Seed: first Super Admin ---- */
const { c } = db.prepare("SELECT COUNT(*) AS c FROM users").get();
if (c === 0) {
  db.prepare(
    `INSERT INTO users (name, email, role, password_hash, must_change_password, status)
     VALUES (?, ?, ?, ?, 0, 'active')`
  ).run("Soham Dhokiya", "soham@infyappdevelopment.com", "Super Admin", bcrypt.hashSync("admin123", 10));
  console.log("Seeded first Super Admin → soham@infyappdevelopment.com / admin123");
}

/* ---- Seed: demo projects + keywords so the dashboard isn't empty ---- */
const { pc } = db.prepare("SELECT COUNT(*) AS pc FROM projects").get();
if (pc === 0) {
  const addProject = db.prepare("INSERT INTO projects (name, active) VALUES (?, ?)");
  const addKw = db.prepare(
    `INSERT INTO keywords (project_id, term, current_rank, previous_rank, last_checked)
     VALUES (?, ?, ?, ?, ?)`
  );

  const sattva = addProject.run("Sattva Connect", 1).lastInsertRowid;
  addKw.run(sattva, "online yoga classes", 4, 9, "2026-06-10");
  addKw.run(sattva, "yoga teacher training online", 12, 8, "2026-06-10");
  addKw.run(sattva, "meditation app for beginners", 21, 21, "2026-06-10");
  addKw.run(sattva, "pranayama breathing course", 3, null, "2026-06-11");

  const bloom = addProject.run("Urban Bloom Florists", 1).lastInsertRowid;
  addKw.run(bloom, "same day flower delivery mumbai", 7, 11, "2026-06-09");

  addProject.run("Peak Performance Gym", 0);
  console.log("Seeded demo projects + keywords");
}

export default db;
