/* ════════════════════════════════════════════════════════════════════
   API ENTRY POINT — wires middleware and routes into an HTTP server.

   Request lifecycle, in order:
     1. express.json()  — parses the JSON body into req.body
     2. route matching  — /api/auth/* or /api/users/*
     3. route-level middleware (requireAuth, requireRole) say yes/no
     4. the handler talks to the DB and responds
     5. the error handler catches anything thrown along the way
   ════════════════════════════════════════════════════════════════════ */
import express from "express";
import { PORT } from "./config.js";
import authRoutes from "./routes/auth.routes.js";
import userRoutes from "./routes/users.routes.js";
import projectRoutes from "./routes/projects.routes.js";

const app = express();

app.use(express.json());

app.use("/api/auth", authRoutes);
app.use("/api/users", userRoutes);
app.use("/api/projects", projectRoutes);

// Anything that didn't match a route above
app.use((req, res) => res.status(404).json({ error: "Not found." }));

// Central error handler: unexpected throws end up here, the client
// gets a clean message, and the real error stays in the server log.
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: "Something went wrong on our side." });
});

app.listen(PORT, () => {
  console.log(`RankBoard API running on http://localhost:${PORT}`);
});
