/* ════════════════════════════════════════════════════════════════════
   PROJECT DASHBOARD — fixed left rail + content area.

   NAV_GROUPS is the extension point: the next SEO tool (backlinks,
   site audit…) is one entry there plus one conditional block in
   <main>. The Rank Ledger fetches its data from the API, derives its
   stats at render time, and refetches after every mutation.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useState } from "react";
import {
  BarChart3,
  Camera,
  RefreshCw,
  Upload,
  FileSpreadsheet,
  Download,
  ChevronDown,
  ChevronLeft,
  Globe,
  ListOrdered,
  LoaderCircle,
  LogOut,
  Minus,
  Plus,
  Search,
  SearchCheck,
  ShieldCheck,
  Trash2,
  TrendingDown,
  TrendingUp,
  Users,
  UserPlus,
  UserCheck,
  Clock,
  X,
} from "lucide-react";
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { api, getToken } from "../api";
import { Modal, ErrorNote, can, INPUT_CLS, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { MozOverview } from "./MozOverview";

// Sidebar navigation, GA4-style: collapsible groups whose sub-items each select
// a view in the main area. A group given no `children` becomes a plain clickable
// nav item (single-view tool). The next SEO tool (backlinks, site audit…) is one
// entry here plus one conditional block in <main>.
const NAV_GROUPS = [
  {
    id: "traffic",
    label: "Traffic",
    icon: Globe,
    children: [
      { id: "traffic-overview", label: "Overview" },
      { id: "traffic-audience", label: "Audience" },
      { id: "traffic-technology", label: "Technology" },
      { id: "traffic-pages", label: "Pages" },
    ],
  },
  {
    id: "rank-ledger",
    label: "Rank Ledger",
    icon: ListOrdered,
    children: [
      { id: "rank-live", label: "Live Ledger" },
      { id: "rank-snapshots", label: "Snapshots" },
    ],
  },
  // Childless group → plain clickable single-view tool (its own page below).
  {
    id: "search-console",
    label: "Search Console",
    icon: SearchCheck,
  },
  // Childless group → the Moz domain-authority overview (single-view tool).
  {
    id: "authority",
    label: "Authority",
    icon: ShieldCheck,
  },
  // { id: "backlinks", label: "Backlinks", icon: Link2 },  ← next tool goes here
];

// The nav group whose children include `navId` (used to default-expand it).
function groupOf(navId) {
  return NAV_GROUPS.find((g) => (g.children || []).some((c) => c.id === navId));
}

export function ProjectDashboard({ user, projectId, onBack, onLogout }) {
  const [project, setProject] = useState(null);
  const [error, setError] = useState(null);
  const [activeNav, setActiveNav] = useState("traffic-overview");
  // Which collapsible nav groups are open. Default: the group holding the
  // initial view, so Traffic starts expanded on Overview.
  const [openGroups, setOpenGroups] = useState(() => {
    const g = groupOf("traffic-overview");
    return g ? [g.id] : [];
  });
  const toggleGroup = (id) =>
    setOpenGroups((open) => (open.includes(id) ? open.filter((x) => x !== id) : [...open, id]));

  const refresh = async () => {
    try {
      const d = await api(`/projects/${projectId}`);
      setProject(d.project);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    refresh();
  }, [projectId]);

  if (!project) {
    return (
      <div className="min-h-screen bg-stone-100 flex flex-col items-center justify-center gap-4 p-6">
        {error ? (
          <>
            <p className="text-sm text-stone-600">{error}</p>
            <button onClick={onBack} className={`${BTN_PRIMARY} px-4 py-2`}>
              Back to projects
            </button>
          </>
        ) : (
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-stone-100 lg:pl-64">
      {/* ── Fixed sidebar (desktop) — light premium rail ── */}
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 bg-white border-r border-stone-200 flex-col">
        <div className="p-4 border-b border-stone-200">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-xs text-stone-400 hover:text-stone-700 mb-4 transition-colors"
          >
            <ChevronLeft size={14} /> All projects
          </button>
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-orange-600 flex items-center justify-center shrink-0 shadow-sm">
              <BarChart3 size={17} className="text-white" />
            </div>
            <div className="min-w-0">
              <p className="text-stone-900 text-sm font-semibold leading-tight truncate font-display">{project.name}</p>
              <p className="text-xs text-stone-500 flex items-center gap-1.5 mt-0.5">
                <span className={`h-1.5 w-1.5 rounded-full ${project.active ? "bg-emerald-500" : "bg-stone-300"}`} />
                {project.active ? "Active" : "Inactive"}
              </p>
              {project.domain && <p className="text-xs text-stone-400 font-data truncate mt-0.5">{project.domain}</p>}
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 overflow-y-auto">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-2">SEO tools</p>
          {NAV_GROUPS.map((group) => {
            const children = group.children || null;

            // Childless group → plain clickable nav item (single-view tool).
            if (!children) {
              return (
                <button
                  key={group.id}
                  onClick={() => setActiveNav(group.id)}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 mb-1 rounded-lg text-sm font-medium transition-colors ${
                    activeNav === group.id
                      ? "bg-orange-50 text-orange-700"
                      : "text-stone-500 hover:text-stone-900 hover:bg-stone-100"
                  }`}
                >
                  <group.icon size={16} /> {group.label}
                </button>
              );
            }

            const expanded = openGroups.includes(group.id);
            const groupActive = children.some((c) => c.id === activeNav);
            return (
              <div key={group.id} className="mb-1">
                <button
                  onClick={() => toggleGroup(group.id)}
                  aria-expanded={expanded}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    groupActive ? "text-stone-900" : "text-stone-500 hover:text-stone-900 hover:bg-stone-100"
                  }`}
                >
                  <group.icon size={16} />
                  <span className="flex-1 text-left">{group.label}</span>
                  <ChevronDown size={14} className={`transition-transform ${expanded ? "" : "-rotate-90"}`} />
                </button>
                {expanded && (
                  <div className="mt-0.5 ml-[1.6rem] pl-3 border-l border-stone-200 flex flex-col gap-0.5">
                    {children.map((child) => (
                      <button
                        key={child.id}
                        onClick={() => setActiveNav(child.id)}
                        className={`w-full text-left px-3 py-1.5 rounded-lg text-sm transition-colors ${
                          activeNav === child.id
                            ? "bg-orange-50 text-orange-700 font-medium"
                            : "text-stone-500 hover:text-stone-900 hover:bg-stone-100"
                        }`}
                      >
                        {child.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="p-4 border-t border-stone-200 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="h-8 w-8 rounded-full bg-orange-100 text-orange-700 flex items-center justify-center text-xs font-semibold shrink-0">
              {user.name?.[0]?.toUpperCase() || "?"}
            </div>
            <div className="min-w-0">
              <p className="text-sm text-stone-900 truncate font-medium">{user.name}</p>
              <p className="text-xs text-stone-400">{user.role}</p>
            </div>
          </div>
          <button
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out"
            className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors shrink-0"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      {/* ── Compact header (mobile) — same nav, light theme ── */}
      <div className="lg:hidden bg-white border-b border-stone-200 sticky top-0 z-20">
        <div className="px-4 pt-4 pb-3 flex items-center justify-between gap-3">
          <button onClick={onBack} className="flex items-center gap-1 text-xs text-stone-500 hover:text-stone-900">
            <ChevronLeft size={14} /> Projects
          </button>
          <p className="text-sm font-semibold text-stone-900 truncate font-display">{project.name}</p>
          <button onClick={onLogout} aria-label="Sign out" className="p-1 text-stone-400 hover:text-stone-900">
            <LogOut size={15} />
          </button>
        </div>
        <div className="px-4 pb-3 flex gap-2 overflow-x-auto">
          {NAV_GROUPS.flatMap((group) =>
            (group.children || [{ id: group.id, label: group.label }]).map((child) => (
              <button
                key={child.id}
                onClick={() => setActiveNav(child.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                  activeNav === child.id
                    ? "bg-orange-600 text-white"
                    : "bg-stone-100 text-stone-600 hover:bg-stone-200"
                }`}
              >
                <group.icon size={13} /> {child.label}
              </button>
            ))
          )}
        </div>
      </div>

      <main className="px-6 py-6">
        {activeNav === "rank-live" && <RankLedger user={user} project={project} onChanged={refresh} />}
        {activeNav === "rank-snapshots" && <SnapshotsView user={user} project={project} />}
        {activeNav.startsWith("traffic-") && (
          <TrafficTool project={project} view={activeNav.slice("traffic-".length)} />
        )}
        {activeNav === "search-console" && <SearchConsoleTool project={project} />}
        {activeNav === "authority" && <MozOverview project={project} />}
      </main>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   RANK LEDGER — where each keyword stands now vs. the previous
   lookup. Lower rank = better (#1 is the top result), so the delta
   is previous − current: +5 means "moved up 5 spots".
   ════════════════════════════════════════════════════════════════════ */

function RankLedger({ user, project, onChanged }) {
  const [showAdd, setShowAdd] = useState(false);
  const [recordFor, setRecordFor] = useState(null); // keyword being re-checked
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);
  const [showImport, setShowImport] = useState(false);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("");
  const kws = project.keywords;

  // Filter the rows by keyword term as the user types (case-insensitive).
  const query = filter.trim().toLowerCase();
  const visibleKws = query ? kws.filter((k) => k.term.toLowerCase().includes(query)) : kws;

  const mayAdd = can(user, "addKeyword");
  const mayDelete = can(user, "deleteKeyword");
  const readOnly = !mayAdd && !mayDelete;

  // Derived stats — computed from the data on every render, never stored.
  const improved = kws.filter((k) => k.previousRank != null && k.currentRank < k.previousRank).length;
  const declined = kws.filter((k) => k.previousRank != null && k.currentRank > k.previousRank).length;
  const ranked = kws.filter((k) => k.currentRank != null);
  const avg = ranked.length ? (ranked.reduce((s, k) => s + k.currentRank, 0) / ranked.length).toFixed(1) : "—";

  const runCheck = async () => {
    setChecking(true);
    setError(null);
    setCheckResult(null);
    try {
      const d = await api(`/projects/${project.id}/check-ranks`, { method: "POST" });
      setCheckResult(d);
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setChecking(false);
    }
  };

  const deleteKeyword = async (kwId) => {
    try {
      await api(`/projects/${project.id}/keywords/${kwId}`, { method: "DELETE" });
      await onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  // Action buttons shared between the toolbar (next to the search bar) and
  // the empty state. Gated by the same write permission as before.
  const actions = mayAdd && (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={runCheck}
        disabled={checking || kws.length === 0}
        title="Look up every keyword's current Google position and record it"
        className={`${BTN_GHOST} px-4 py-2 disabled:opacity-40 disabled:cursor-not-allowed`}
      >
        {checking ? <LoaderCircle size={15} className="animate-spin" /> : <RefreshCw size={15} />} Check rankings
      </button>
      <button
        onClick={() => setShowImport(true)}
        title="Bulk import keywords from an Excel file"
        className={`${BTN_GHOST} px-4 py-2`}
      >
        <Upload size={15} /> Import
      </button>
      <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
        <Plus size={16} /> Add keyword
      </button>
    </div>
  );

  return (
    <div className="w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">
          Rank Ledger
          {readOnly && (
            <span className="ml-2 align-middle text-xs font-medium px-2 py-0.5 rounded-full bg-stone-200 text-stone-600">
              View only
            </span>
          )}
        </h1>
        <p className="text-sm text-stone-500 mt-1">Where each keyword stands now vs. the previous lookup.</p>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {checkResult && (
        <div className="text-sm rounded-lg px-3 py-2 mb-4 bg-sky-50 border border-sky-100 text-sky-800">
          {checkResult.source === "simulated"
            ? "Simulated lookup (no DataForSEO credentials configured) — "
            : "Live DataForSEO lookup — "}
          updated {checkResult.updated} of {checkResult.checked} keyword{checkResult.checked === 1 ? "" : "s"}.
          {checkResult.notFound.length > 0 && (
            <> Not found in checked depth: {checkResult.notFound.join(", ")} — those rows were left unchanged.</>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6 mt-2">
        <Stat label="Tracked" value={kws.length} />
        <Stat label="Improved" value={improved} tone="up" />
        <Stat label="Declined" value={declined} tone="down" />
        <Stat label="Avg. position" value={avg} />
      </div>

      {(mayAdd || kws.length > 0) && (
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          {kws.length > 0 ? (
            <div className="relative w-full sm:w-auto sm:flex-1 sm:max-w-xs">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 pointer-events-none" />
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter keywords…"
                aria-label="Filter keywords"
                className="w-full pl-9 pr-9 py-2 text-sm rounded-lg border border-stone-200 bg-white text-stone-800 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-orange-500/40 focus:border-orange-400"
              />
              {filter && (
                <button
                  onClick={() => setFilter("")}
                  aria-label="Clear filter"
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded text-stone-300 hover:text-stone-600 transition-colors"
                >
                  <X size={15} />
                </button>
              )}
            </div>
          ) : (
            <div className="hidden sm:block" />
          )}
          {actions}
        </div>
      )}

      {kws.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <Search size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No keywords yet</h3>
          {mayAdd ? (
            <>
              <p className="text-sm text-stone-500 mt-1 mb-5 max-w-xs">
                Add the search terms you want to track and the ledger fills in from there.
              </p>
              <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
                <Plus size={15} /> Add your first keyword
              </button>
            </>
          ) : (
            <p className="text-sm text-stone-500 mt-1 max-w-xs">The team hasn't started tracking keywords here yet.</p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
                <th className="px-5 py-3 font-medium">Keyword</th>
                <th className="px-5 py-3 font-medium">Previous</th>
                <th className="px-5 py-3 font-medium">Current</th>
                <th className="px-5 py-3 font-medium">Change</th>
                <th className="px-5 py-3 font-medium">Last checked</th>
                {(mayAdd || mayDelete) && <th className="px-2 py-3" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {visibleKws.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-sm text-stone-400">
                    No keywords match &ldquo;{filter.trim()}&rdquo;.
                  </td>
                </tr>
              )}
              {visibleKws.map((k) => (
                <tr key={k.id} className="hover:bg-stone-50">
                  <td className="px-5 py-3 font-medium text-stone-800">{k.term}</td>
                  <td className="px-5 py-3 text-stone-400 font-data">
                    {checking ? (
                      <span className="skeleton inline-block h-4 w-8 align-middle" />
                    ) : k.previousRank == null ? (
                      "—"
                    ) : (
                      `#${k.previousRank}`
                    )}
                  </td>
                  <td className="px-5 py-3 font-data font-semibold text-stone-900">
                    {checking ? (
                      <span className="skeleton inline-block h-4 w-8 align-middle" />
                    ) : k.currentRank == null ? (
                      <span className="text-stone-300">—</span>
                    ) : (
                      `#${k.currentRank}`
                    )}
                  </td>
                  <td className="px-5 py-3">
                    {checking ? (
                      <span className="skeleton inline-block h-4 w-12 align-middle" />
                    ) : (
                      <RankChange current={k.currentRank} previous={k.previousRank} />
                    )}
                  </td>
                  <td className="px-5 py-3 text-stone-400 text-xs whitespace-nowrap">
                    {checking ? <span className="skeleton inline-block h-3 w-20 align-middle" /> : k.lastChecked}
                  </td>
                  {(mayAdd || mayDelete) && (
                    <td className="px-2 py-3">
                      <span className="flex items-center justify-end gap-0.5">
                        {mayAdd && (
                          <button
                            onClick={() => setRecordFor(k)}
                            aria-label={`Record new rank for ${k.term}`}
                            title="Record new rank (current becomes previous)"
                            className="p-1 rounded text-stone-300 hover:text-orange-600 transition-colors"
                          >
                            <RefreshCw size={14} />
                          </button>
                        )}
                        {mayDelete && (
                          <button
                            onClick={() => deleteKeyword(k.id)}
                            aria-label={`Remove ${k.term}`}
                            title="Remove keyword"
                            className="p-1 rounded text-stone-300 hover:text-red-500 transition-colors"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </span>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-stone-400 mt-4">
        "Check rankings" runs in free simulated mode until DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD are set on the server, then it does real Google lookups for this project&apos;s domain. A scheduled job can later call the same endpoint automatically.
      </p>

      {recordFor && (
        <RecordRankModal
          projectId={project.id}
          keyword={recordFor}
          onClose={() => setRecordFor(null)}
          onSaved={() => {
            setRecordFor(null);
            onChanged();
          }}
        />
      )}

      {showAdd && (
        <AddKeywordModal
          projectId={project.id}
          onClose={() => setShowAdd(false)}
          onAdded={() => {
            setShowAdd(false);
            onChanged();
          }}
        />
      )}

      {showImport && (
        <BulkImportModal
          projectId={project.id}
          onClose={() => setShowImport(false)}
          onImported={onChanged}
        />
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   SNAPSHOTS — read-only monthly freezes of the ledger.

   On mount we load the list (newest first) and auto-select the latest.
   Picking a month fetches that snapshot and renders a plain table that
   REUSES the Live Ledger's table styling, trimmed to the three frozen
   columns. "Save this month" captures the current ranks; if the month
   already exists we confirm before replacing it. The button is gated by
   the same write permission the rest of the ledger uses (addKeyword).
   This view is comparison/export-free by design — that's a later phase.
   ════════════════════════════════════════════════════════════════════ */
function SnapshotsView({ user, project }) {
  const [snapshots, setSnapshots] = useState(null); // null = still loading
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null); // selected snapshot + its rows
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const maySave = can(user, "addKeyword");

  const loadList = async (selectId) => {
    try {
      const d = await api(`/projects/${project.id}/snapshots`);
      setSnapshots(d.snapshots);
      setError(null);
      if (selectId != null) setSelectedId(selectId);
      else if (d.snapshots.length) setSelectedId((prev) => prev ?? d.snapshots[0].id);
      return d.snapshots;
    } catch (err) {
      setError(err.message);
      setSnapshots([]);
    }
  };

  // Load the list once per project.
  useEffect(() => {
    loadList();
  }, [project.id]);

  // Fetch the selected snapshot's rows whenever the selection changes.
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    api(`/projects/${project.id}/snapshots/${selectedId}`)
      .then((d) => !cancelled && setDetail(d.snapshot))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [selectedId, project.id]);

  const save = async () => {
    // The server picks the month authoritatively; we compute the current
    // key only to decide whether to warn about replacing an existing one.
    const now = new Date();
    const periodKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const exists = (snapshots || []).some((s) => s.periodKey === periodKey);
    if (exists && !window.confirm("Replace this month's snapshot?")) return;

    setSaving(true);
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/snapshots`, { method: "POST" });
      await loadList(d.snapshot.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h2 className="text-xl font-bold text-stone-900 tracking-tight font-display">Snapshots</h2>
          <p className="text-sm text-stone-500 mt-1">A frozen copy of every keyword&apos;s rank, saved per month.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {snapshots && snapshots.length > 0 && (
            <select
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}
              aria-label="Choose a saved month"
              className={`${INPUT_CLS} w-auto`}
            >
              {snapshots.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label} ({s.keywordCount} keyword{s.keywordCount === 1 ? "" : "s"})
                </option>
              ))}
            </select>
          )}
          {maySave && (
            <button
              onClick={save}
              disabled={saving}
              title="Freeze the current ranks for this month"
              className={`${BTN_PRIMARY} px-4 py-2`}
            >
              {saving ? <LoaderCircle size={15} className="animate-spin" /> : <Camera size={15} />} Save this month
            </button>
          )}
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {snapshots === null ? (
        <div className="flex justify-center py-16">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : snapshots.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <Camera size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No snapshots yet</h3>
          <p className="text-sm text-stone-500 mt-1 max-w-xs">
            {maySave ? "Save this month to create your first." : "No months have been saved here yet."}
          </p>
        </div>
      ) : (
        <>
          {detail && (
            <p className="text-xs text-stone-400 mb-3">
              {detail.label} · captured {detail.capturedAt} · {detail.keywordCount} keyword
              {detail.keywordCount === 1 ? "" : "s"}
            </p>
          )}
          <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
                  <th className="px-5 py-3 font-medium">Keyword</th>
                  <th className="px-5 py-3 font-medium">Rank</th>
                  <th className="px-5 py-3 font-medium">Last checked</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {!detail ? (
                  <tr>
                    <td colSpan={3} className="px-5 py-10 text-center">
                      <LoaderCircle size={18} className="text-orange-600 animate-spin inline" />
                    </td>
                  </tr>
                ) : detail.ranks.length === 0 ? (
                  <tr>
                    <td colSpan={3} className="px-5 py-10 text-center text-sm text-stone-400">
                      No keywords were tracked when this snapshot was saved.
                    </td>
                  </tr>
                ) : (
                  detail.ranks.map((r, i) => (
                    <tr key={i} className="hover:bg-stone-50">
                      <td className="px-5 py-3 font-medium text-stone-800">{r.term}</td>
                      <td className="px-5 py-3 font-data font-semibold text-stone-900">
                        {r.rank == null ? <span className="text-stone-300">—</span> : `#${r.rank}`}
                      </td>
                      <td className="px-5 py-3 text-stone-400 text-xs whitespace-nowrap">{r.lastChecked ?? "—"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   TRAFFIC (GA4) — per-project Google Analytics 4 traffic for a chosen
   date range. A shared date-range picker sits at the top; each nav
   sub-view (Overview / Audience / Technology / Pages) is then the FULL
   Explore report builder, pre-set to that page's default dimension (see
   VIEW_DEFAULT_DIMENSION) and managing its own dimensions / metrics /
   filters. Overview additionally shows the headline metric cards (Active
   Users, New Users, Returning Users, Avg Engagement Time) and the
   "Users over time" trend above its builder, fed by /api/projects/:id/
   analytics. When the project has no GA4 property ID — or the server says
   GA4 isn't configured — we show a friendly empty state rather than an error.
   ════════════════════════════════════════════════════════════════════ */

// Each Traffic nav sub-view IS the full Explore report builder, pre-set to this
// default GA4 dimension; the user can then change dimensions, metrics and
// filters freely from there.
const VIEW_DEFAULT_DIMENSION = {
  overview: "sessionDefaultChannelGroup",
  audience: "country",
  technology: "deviceCategory",
  pages: "landingPagePlusQueryString",
};

// Dimension picker, organised like GA4's own menu: category ->
// [user-facing label, GA4 API name]. The API names match the backend's
// ALLOWED_DIMENSIONS allowlist exactly; selecting one runs a breakdown
// report for that dimension with our three standard metrics.
const DIMENSION_GROUPS = {
  "Geography": [["Country", "country"], ["Region", "region"], ["City", "city"], ["Continent", "continent"], ["Language", "language"]],
  "Traffic source (session)": [["Default Channel Group", "sessionDefaultChannelGroup"], ["Source", "sessionSource"], ["Medium", "sessionMedium"], ["Source / Medium", "sessionSourceMedium"], ["Campaign", "sessionCampaignName"]],
  "Traffic source (first user)": [["Default Channel Group", "firstUserDefaultChannelGroup"], ["Source", "firstUserSource"], ["Medium", "firstUserMedium"], ["Campaign", "firstUserCampaignName"]],
  "Platform / device": [["Device Category", "deviceCategory"], ["Operating System", "operatingSystem"], ["OS + Version", "operatingSystemWithVersion"], ["Browser", "browser"], ["Platform", "platform"], ["Screen Resolution", "screenResolution"], ["Device Model", "mobileDeviceModel"], ["Device Brand", "mobileDeviceBranding"]],
  "Page / screen": [["Landing Page", "landingPagePlusQueryString"], ["Page Path", "pagePath"], ["Page Path + Query", "pagePathPlusQueryString"], ["Page Title", "pageTitle"], ["Full Page URL", "fullPageUrl"], ["Hostname", "hostName"]],
  "User": [["New vs Returning", "newVsReturning"], ["Signed In With User ID", "signedInWithUserId"], ["Audience", "audienceName"]],
  "Time": [["Date", "date"], ["Date + Hour", "dateHour"], ["Hour", "hour"], ["Day of Week", "dayOfWeekName"], ["Week", "week"], ["Month", "month"], ["Year", "year"]],
  "Demographics (needs Google Signals)": [["Age", "userAgeBracket"], ["Gender", "userGender"], ["Interests", "brandingInterest"]],
};

// Metric picker for the report builder: user-facing label -> GA4 metric API
// name. The API names match the backend's ALLOWED_METRICS allowlist exactly.
const METRICS = {
  "Active Users": "activeUsers",
  "New Users": "newUsers",
  "Total Users": "totalUsers",
  "Sessions": "sessions",
  "Engaged Sessions": "engagedSessions",
  "Engagement Rate": "engagementRate",
  "Avg Session Duration": "averageSessionDuration",
  "User Engagement Duration": "userEngagementDuration",
  "Views": "screenPageViews",
  "Event Count": "eventCount",
  "Bounce Rate": "bounceRate",
  "Key Events": "keyEvents",
  "Total Revenue": "totalRevenue",
  "Engaged Sessions / Active User": "engagedSessionsPerUser",
};

// Filter operators (GA4 StringFilter match types): [user-facing label, matchType].
// matchType matches the backend's ALLOWED_MATCH_TYPES allowlist exactly.
const OPERATORS = [
  ["exactly matches", "EXACT"],
  ["contains", "CONTAINS"],
  ["begins with", "BEGINS_WITH"],
  ["ends with", "ENDS_WITH"],
  ["matches regex", "FULL_REGEXP"],
];

// The user-facing label for a GA4 API name (for the section title + table
// column header). Falls back to the raw name if somehow not found.
function dimensionLabel(apiName) {
  for (const items of Object.values(DIMENSION_GROUPS)) {
    for (const [label, name] of items) {
      if (name === apiName) return label;
    }
  }
  return apiName;
}

// The user-facing label for a GA4 metric API name (table header). Falls back
// to the raw name if somehow not found.
function metricLabel(apiName) {
  for (const [label, name] of Object.entries(METRICS)) {
    if (name === apiName) return label;
  }
  return apiName;
}

// Rate metrics are fractions (0–1) GA reports as percentages; duration metrics
// are seconds. Everything else is a plain count. Used for the table cells.
const RATE_METRICS = new Set(["engagementRate", "bounceRate"]);
const DURATION_METRICS = new Set(["averageSessionDuration", "userEngagementDuration"]);

function formatMetric(name, value) {
  if (value == null) return "0";
  if (RATE_METRICS.has(name)) return `${(Number(value) * 100).toFixed(1)}%`;
  if (DURATION_METRICS.has(name)) return formatEngagement(value);
  // Revenue as currency ("$0.00"); the engaged-sessions/user ratio as 2 dp.
  if (name === "totalRevenue") {
    return `$${(Number(value) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (name === "engagedSessionsPerUser") return (Number(value) || 0).toFixed(2);
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : String(value);
}

// Demographics dimensions need Google Signals enabled in GA4 — used to add
// a hint to the "not available" message for those.
const DEMOGRAPHICS_NAMES = new Set(
  DIMENSION_GROUPS["Demographics (needs Google Signals)"].map(([, name]) => name)
);

const RANGE_PRESETS = [
  { days: 7, label: "Last 7 days" },
  { days: 28, label: "Last 28 days" },
  { days: 90, label: "Last 90 days" },
];

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Chart palette — orange is the app accent; sky is the established second
// series colour (see role styles / rank "New" badge).
const COLOR_ACTIVE = "#5b5bf7"; // brand purple — active users
const COLOR_NEW = "#0284c7"; // sky-600 — new users

// Categorical palette for composition donuts (Channels, Devices, Language…).
// Leads with the two series colours, then distinct hues; greens/reds are left
// out — those are reserved app-wide for rank movement. "Other" uses stone-400.
const DONUT_COLORS = ["#5b5bf7", "#0284c7", "#f59e0b", "#7c3aed", "#0891b2", "#db2777", "#4f46e5", "#475569"];

// Seconds → "1m 23s" (or "23s" under a minute), matching GA's display.
function formatEngagement(seconds) {
  const total = Math.round(Number(seconds) || 0);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// Local YYYY-MM-DD (no UTC shift — GA ranges are calendar dates).
function toYMD(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// "Last N days" ending today (inclusive), as concrete dates.
function presetRange(days) {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - (days - 1));
  return { start: toYMD(start), end: toYMD(end) };
}

function parseYMD(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

// "May 1 – May 28, 2026" (year shown once when both ends share it).
function formatRangeLabel(start, end) {
  const a = parseYMD(start);
  const b = parseYMD(end);
  const sameYear = a.getFullYear() === b.getFullYear();
  const left = `${MONTH_NAMES[a.getMonth()]} ${a.getDate()}${sameYear ? "" : `, ${a.getFullYear()}`}`;
  const right = `${MONTH_NAMES[b.getMonth()]} ${b.getDate()}, ${b.getFullYear()}`;
  return `${left} – ${right}`;
}

// Raw GA date "20260501" → "05/01" for chart axes/tooltips.
function formatGADate(raw) {
  if (!raw || raw.length !== 8) return raw || "";
  return `${raw.slice(4, 6)}/${raw.slice(6, 8)}`;
}

// Month + From/To fields. Shares the pills' height (h-9), border, rounding,
// padding and font so the whole control sits on one consistent baseline.
const RANGE_FIELD_CLS =
  "h-9 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-colors";

function TrafficTool({ project, view }) {
  const [range, setRange] = useState(() => presetRange(28)); // default: last 28 days
  const [activePreset, setActivePreset] = useState(28); // highlighted preset, or null
  const [data, setData] = useState(null); // null = still loading
  const [error, setError] = useState(null);

  // The Overview headline cards + trend follow the shared date range. (Each
  // page's builder fetches its own filtered /report independently below.)
  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError(null);
    api(`/projects/${project.id}/analytics`, {
      method: "POST",
      body: { start: range.start, end: range.end },
    })
      .then((d) => !cancelled && setData(d.analytics))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [project.id, range.start, range.end]);

  // No property ID set, or the server reports GA4 isn't configured → empty state.
  const notConfigured = !project.gaPropertyId || (data && data.configured === false);

  const applyPreset = (days) => {
    setActivePreset(days);
    setRange(presetRange(days));
  };

  // <input type="month"> "2026-05" → the whole calendar month.
  const applyMonth = (ym) => {
    if (!ym) return;
    const [y, m] = ym.split("-").map(Number);
    const lastDay = new Date(y, m, 0).getDate(); // day 0 of next month = last of this
    setActivePreset(null);
    setRange({ start: `${ym}-01`, end: `${ym}-${String(lastDay).padStart(2, "0")}` });
  };

  const applyCustom = (which, value) => {
    if (!value) return;
    setActivePreset(null);
    setRange((r) => ({ ...r, [which]: value }));
  };

  // Purely presentational: when the current range is exactly one calendar
  // month, show it in the month picker (e.g. "June 2026") instead of the
  // native blank field. Doesn't affect the dates, modes, or the fetch.
  const monthValue = (() => {
    if (activePreset !== null) return "";
    const s = parseYMD(range.start);
    const e = parseYMD(range.end);
    const lastDay = new Date(s.getFullYear(), s.getMonth() + 1, 0).getDate();
    const isFullMonth =
      s.getDate() === 1 &&
      s.getFullYear() === e.getFullYear() &&
      s.getMonth() === e.getMonth() &&
      e.getDate() === lastDay;
    return isFullMonth ? range.start.slice(0, 7) : "";
  })();

  return (
    <div className="w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">Traffic</h1>
        <p className="text-sm text-stone-500 mt-1">
          Google Analytics 4 active users, new users, and average engagement time for the selected range.
        </p>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {notConfigured ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <Globe size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No GA4 traffic yet</h3>
          <p className="text-sm text-stone-500 mt-1 max-w-xs">
            {data && data.message ? data.message : "Add this project's GA4 property ID to see traffic."}
          </p>
        </div>
      ) : (
        <>
          {/* ── Date-range control ── */}
          <div className="bg-white rounded-xl border border-stone-200 p-4 mb-6">
            {/* Presets — a tidy pill group; only the active mode is highlighted. */}
            <div className="flex flex-wrap items-center gap-2">
              {RANGE_PRESETS.map((p) => {
                const active = activePreset === p.days;
                return (
                  <button
                    key={p.days}
                    onClick={() => applyPreset(p.days)}
                    aria-pressed={active}
                    className={`h-9 px-4 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 ${
                      active
                        ? "bg-orange-600 text-white border-orange-600"
                        : "bg-white text-stone-600 border-stone-300 hover:border-stone-400 hover:text-stone-800"
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>

            {/* Month + custom range — same baseline as the pills, own labelled
                line, wraps gracefully on narrow screens. */}
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-stone-100 mt-3 pt-3">
              <label className="flex items-center gap-2 text-sm text-stone-500">
                <span className="font-medium text-stone-600">Month:</span>
                <input
                  type="month"
                  value={monthValue}
                  onChange={(e) => applyMonth(e.target.value)}
                  aria-label="Pick a month"
                  className={RANGE_FIELD_CLS}
                />
              </label>

              <span className="hidden sm:block h-5 w-px bg-stone-200" />

              <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-stone-500">
                <span className="font-medium text-stone-600">Custom range:</span>
                <span className="flex items-center gap-1.5">
                  <span className="text-stone-400">From</span>
                  <input
                    type="date"
                    value={range.start}
                    max={range.end}
                    onChange={(e) => applyCustom("start", e.target.value)}
                    aria-label="From date"
                    className={RANGE_FIELD_CLS}
                  />
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="text-stone-400">To</span>
                  <input
                    type="date"
                    value={range.end}
                    min={range.start}
                    onChange={(e) => applyCustom("end", e.target.value)}
                    aria-label="To date"
                    className={RANGE_FIELD_CLS}
                  />
                </span>
              </div>
            </div>

            {/* Summary — small, muted, beneath the controls. */}
            <p className="text-xs text-stone-400 mt-3">
              Showing <span className="font-medium text-stone-600">{formatRangeLabel(range.start, range.end)}</span>
            </p>
          </div>

          {/* Overview only: the headline cards + trend, following the shared
              date range. The other pages are just the builder below. */}
          {view === "overview" &&
            (data === null ? (
              <div className="flex justify-center py-16">
                <LoaderCircle size={22} className="text-orange-600 animate-spin" />
              </div>
            ) : data.error ? (
              <div className="text-sm rounded-lg px-3 py-2 mb-6 bg-amber-50 border border-amber-100 text-amber-800">
                {data.error}
              </div>
            ) : (
              (() => {
                // Sparklines come straight from the real per-day series — no
                // invented comparison numbers. Returning = active − new per day.
                const rows = data.byDate?.rows || [];
                const active = rows.map((r) => Number(r.activeUsers) || 0);
                const fresh = rows.map((r) => Number(r.newUsers) || 0);
                const returning = rows.map((_, i) => Math.max(0, active[i] - fresh[i]));
                return (
                  <div className="space-y-6 mb-6">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4">
                      <Stat label="Active users" value={(data.summary?.activeUsers ?? 0).toLocaleString()} icon={Users} spark={active} />
                      <Stat label="New users" value={(data.summary?.newUsers ?? 0).toLocaleString()} icon={UserPlus} spark={fresh} />
                      <Stat label="Returning users" value={(data.summary?.returningUsers ?? 0).toLocaleString()} icon={UserCheck} spark={returning} />
                      <Stat label="Avg. engagement time" value={formatEngagement(data.summary?.avgEngagementSeconds)} icon={Clock} />
                    </div>
                    <TrafficTrendChart byDate={data.byDate || { rows: [] }} />
                  </div>
                );
              })()
            ))}

          {/* Every Traffic page IS the full Explore builder, pre-set to that
              page's default dimension. key={view} gives each page its own
              independent instance (fresh dimensions / metrics / filters). */}
          <ExploreReport
            key={view}
            projectId={project.id}
            range={range}
            defaultDimension={VIEW_DEFAULT_DIMENSION[view]}
          />
        </>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   EXPLORE — ONE GA4-style report builder (mirrors GA4's Free-form
   exploration / the Data API runReport). Each Traffic page renders its OWN
   self-contained instance, pre-set via `defaultDimension` to that page's
   default breakdown. The user picks one or more DIMENSIONS (removable chips
   + a categorised DIMENSION_GROUPS menu), one or more METRICS, and N inline
   filter conditions joined by AND/OR, and a SINGLE chart + table shows the
   combined result. The chart type adapts to the selected dimension (donut /
   line / bar — see ReportResult). It auto-runs whenever the dimensions,
   metrics or filter list change, debouncing the filter value text (~500ms)
   so it doesn't fire on every keystroke. GA4 rejects some combinations, so
   the server returns {error} (HTTP 200) and we show a muted message in place
   of the table — never a crash.
   ════════════════════════════════════════════════════════════════════ */
function ExploreReport({ projectId, range, defaultDimension }) {
  const [dimensions, setDimensions] = useState([defaultDimension || "sessionDefaultChannelGroup"]);
  const [metrics, setMetrics] = useState(["activeUsers", "newUsers"]); // defaults
  const [filters, setFilters] = useState([]); // {dimension, operator, value, exclude}
  const [match, setMatch] = useState("AND");
  const [result, setResult] = useState(null); // null = loading
  const [error, setError] = useState(null); // transport/HTTP failure (api() threw)
  const [runNonce, setRunNonce] = useState(0); // bumped by the Run button to force a fetch
  const [openMenu, setOpenMenu] = useState(null); // "dimension" | "metric" | null

  // Debounce the filter VALUE text so typing doesn't fire a request per
  // keystroke. Structural changes (dimensions, metrics, match, a filter's
  // dimension/operator/exclude, adding/removing rows) re-run immediately;
  // only the typed values are delayed ~500ms via this mirror.
  const valueKey = filters.map((f) => f.value).join(" ");
  const [debouncedValueKey, setDebouncedValueKey] = useState(valueKey);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedValueKey(valueKey), 500);
    return () => clearTimeout(t);
  }, [valueKey]);

  // Fingerprints of everything that should re-run the report immediately.
  const dimsKey = dimensions.join(",");
  const metricsKey = metrics.join(",");
  const structuralKey = JSON.stringify(filters.map((f) => [f.dimension, f.operator, f.exclude]));

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError(null);
    // Drop half-built rows (no value yet) so we never send a CONTAINS "".
    const activeFilters = filters
      .filter((f) => f.value.trim() !== "")
      .map((f) => ({ dimension: f.dimension, operator: f.operator, value: f.value, exclude: f.exclude }));
    // Sessions is a permanent column on every report — pin it onto the request
    // even when the user hasn't picked it (appended last so it never changes
    // the first metric the chart/ordering uses).
    const reportMetrics = metrics.includes("sessions") ? metrics : [...metrics, "sessions"];
    api(`/projects/${projectId}/analytics/report`, {
      method: "POST",
      body: { start: range.start, end: range.end, dimensions, metrics: reportMetrics, filters: activeFilters, match, limit: 250 },
    })
      .then((d) => !cancelled && setResult(d.report))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, range.start, range.end, dimsKey, metricsKey, match, structuralKey, debouncedValueKey, runNonce]);

  // ── Dimension / metric chip helpers (always keep at least one of each) ──
  const addDimension = (name) => {
    setOpenMenu(null);
    setDimensions((d) => (d.includes(name) ? d : [...d, name]));
  };
  const removeDimension = (name) => setDimensions((d) => (d.length > 1 ? d.filter((x) => x !== name) : d));
  const addMetric = (name) => {
    setOpenMenu(null);
    setMetrics((m) => (m.includes(name) ? m : [...m, name]));
  };
  const removeMetric = (name) => setMetrics((m) => (m.length > 1 ? m.filter((x) => x !== name) : m));

  // ── Filter row helpers ──
  const addFilter = () =>
    setFilters((f) => [...f, { dimension: dimensions[0] || "country", operator: "CONTAINS", value: "", exclude: false }]);
  const updateFilter = (i, patch) => setFilters((f) => f.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  const removeFilter = (i) => setFilters((f) => f.filter((_, idx) => idx !== i));

  // The server reports incompatible combinations / no data as {error}; a thrown
  // api() error lands in `error`. Either way we show the same muted message.
  const failed = error || result?.error;
  const usesDemographics = dimensions.some((d) => DEMOGRAPHICS_NAMES.has(d));

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-stone-700 font-display">Explore</h2>
          <p className="text-xs text-stone-400 mt-0.5">
            Build a report from any dimensions, metrics and filters — like GA4&apos;s Free-form exploration.
          </p>
        </div>
        <button onClick={() => setRunNonce((n) => n + 1)} title="Re-run the report now" className={`${BTN_PRIMARY} px-4 py-2`}>
          <RefreshCw size={15} /> Run
        </button>
      </div>

      {/* ── Builder ── */}
      <div className="bg-white rounded-xl border border-stone-200 p-4 mb-4 space-y-4">
        {/* Dimensions */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Dimensions</p>
          <div className="flex flex-wrap items-center gap-2">
            {dimensions.map((name) => (
              <span
                key={name}
                className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-orange-50 border border-orange-200 text-sm text-orange-800"
              >
                {dimensionLabel(name)}
                <button
                  onClick={() => removeDimension(name)}
                  disabled={dimensions.length === 1}
                  aria-label={`Remove ${dimensionLabel(name)}`}
                  className="p-0.5 rounded-full text-orange-400 hover:text-orange-700 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <X size={13} />
                </button>
              </span>
            ))}
            <div className="relative">
              <button
                onClick={() => setOpenMenu(openMenu === "dimension" ? null : "dimension")}
                className={`${BTN_GHOST} px-3 py-1.5 text-sm`}
              >
                <Plus size={14} /> Dimension
              </button>
              {openMenu === "dimension" && (
                <PickerMenu onClose={() => setOpenMenu(null)}>
                  {Object.entries(DIMENSION_GROUPS).map(([category, items]) => (
                    <div key={category} className="py-1">
                      <p className="px-3 py-1 text-xs font-semibold uppercase tracking-wider text-stone-400">{category}</p>
                      {items.map(([optLabel, apiName]) => (
                        <button
                          key={apiName}
                          onClick={() => addDimension(apiName)}
                          disabled={dimensions.includes(apiName)}
                          className="w-full text-left px-3 py-1.5 text-sm text-stone-700 hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          {optLabel}
                        </button>
                      ))}
                    </div>
                  ))}
                </PickerMenu>
              )}
            </div>
          </div>
        </div>

        {/* Metrics */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Metrics</p>
          <div className="flex flex-wrap items-center gap-2">
            {metrics.map((name) => (
              <span
                key={name}
                className="inline-flex items-center gap-1.5 pl-3 pr-1.5 py-1 rounded-full bg-sky-50 border border-sky-200 text-sm text-sky-800"
              >
                {metricLabel(name)}
                <button
                  onClick={() => removeMetric(name)}
                  disabled={metrics.length === 1}
                  aria-label={`Remove ${metricLabel(name)}`}
                  className="p-0.5 rounded-full text-sky-400 hover:text-sky-700 disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  <X size={13} />
                </button>
              </span>
            ))}
            <div className="relative">
              <button
                onClick={() => setOpenMenu(openMenu === "metric" ? null : "metric")}
                className={`${BTN_GHOST} px-3 py-1.5 text-sm`}
              >
                <Plus size={14} /> Metric
              </button>
              {openMenu === "metric" && (
                <PickerMenu onClose={() => setOpenMenu(null)}>
                  <div className="py-1">
                    {Object.entries(METRICS).map(([optLabel, apiName]) => (
                      <button
                        key={apiName}
                        onClick={() => addMetric(apiName)}
                        disabled={metrics.includes(apiName)}
                        className="w-full text-left px-3 py-1.5 text-sm text-stone-700 hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        {optLabel}
                      </button>
                    ))}
                  </div>
                </PickerMenu>
              )}
            </div>
          </div>
        </div>

        {/* Filters — inline, stackable conditions joined by Match ALL / ANY.
            Self-contained in each builder so every Traffic page filters
            independently. The dimension list is the full DIMENSION_GROUPS. */}
        <div>
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-stone-400">Filters</p>
            {filters.length > 0 && (
              <div className="inline-flex rounded-lg border border-stone-300 overflow-hidden text-xs">
                {[["AND", "Match ALL"], ["OR", "Match ANY"]].map(([val, lbl]) => (
                  <button
                    key={val}
                    onClick={() => setMatch(val)}
                    className={`px-3 py-1 font-medium transition-colors ${
                      match === val ? "bg-orange-600 text-white" : "bg-white text-stone-600 hover:bg-stone-50"
                    }`}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
            )}
          </div>

          {filters.length > 0 && (
            <div className="space-y-2">
              {filters.map((f, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <select
                    value={f.dimension}
                    onChange={(e) => updateFilter(i, { dimension: e.target.value })}
                    aria-label="Filter dimension"
                    className={`${RANGE_FIELD_CLS} w-auto max-w-[12rem]`}
                  >
                    {Object.entries(DIMENSION_GROUPS).map(([category, items]) => (
                      <optgroup key={category} label={category}>
                        {items.map(([optLabel, apiName]) => (
                          <option key={apiName} value={apiName}>
                            {optLabel}
                          </option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                  <select
                    value={f.operator}
                    onChange={(e) => updateFilter(i, { operator: e.target.value })}
                    aria-label="Filter operator"
                    className={`${RANGE_FIELD_CLS} w-auto`}
                  >
                    {OPERATORS.map(([lbl, mt]) => (
                      <option key={mt} value={mt}>
                        {lbl}
                      </option>
                    ))}
                  </select>
                  <input
                    type="text"
                    value={f.value}
                    onChange={(e) => updateFilter(i, { value: e.target.value })}
                    placeholder="value"
                    aria-label="Filter value"
                    className={`${RANGE_FIELD_CLS} flex-1 min-w-[8rem]`}
                  />
                  <button
                    onClick={() => updateFilter(i, { exclude: !f.exclude })}
                    title={f.exclude ? "Excluding matches — click to include" : "Including matches — click to exclude"}
                    className={`h-9 px-3 rounded-lg border text-sm font-medium transition-colors ${
                      f.exclude
                        ? "bg-red-50 border-red-200 text-red-600"
                        : "bg-emerald-50 border-emerald-200 text-emerald-700"
                    }`}
                  >
                    {f.exclude ? "Exclude" : "Include"}
                  </button>
                  <button
                    onClick={() => removeFilter(i)}
                    aria-label="Remove filter"
                    className="p-1.5 rounded-md text-stone-300 hover:text-red-500 transition-colors"
                  >
                    <X size={15} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <button onClick={addFilter} className={`${BTN_GHOST} px-3 py-1.5 text-sm mt-2`}>
            <Plus size={14} /> Add filter
          </button>
        </div>
      </div>

      {/* ── Result ── */}
      {result === null && !error ? (
        <div className="flex justify-center py-16">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : failed ? (
        <div className="bg-white rounded-xl border border-stone-200 p-6">
          <p className="text-sm text-stone-400">
            This combination isn&apos;t available, or has no data for this range.
            {usesDemographics && " Demographics require Google Signals to be enabled on the property."}
          </p>
        </div>
      ) : (
        <ReportResult report={result} />
      )}
    </div>
  );
}

/* A small dropdown panel for the dimension/metric pickers: a transparent
   full-screen backdrop closes it on an outside click; the panel floats below
   its trigger. */
function PickerMenu({ children, onClose }) {
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute left-0 top-full mt-1 z-20 w-60 max-h-72 overflow-y-auto rounded-lg border border-stone-200 bg-white shadow-lg">
        {children}
      </div>
    </>
  );
}

/* Headline time-series: active + new users per day, GA-style line chart. */
function TrafficTrendChart({ byDate }) {
  const rows = byDate.rows || [];
  const chartData = rows.map((r) => ({ ...r, label: formatGADate(r.date) }));

  return (
    <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-stone-900 font-display">Users over time</h2>
          <p className="text-xs text-stone-400 mt-0.5">Active vs. new users across the range</p>
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-medium text-stone-600 border border-stone-200 rounded-lg px-2.5 py-1">
          Daily <ChevronDown size={13} className="text-stone-400" />
        </span>
      </div>
      {chartData.length === 0 ? (
        <p className="py-12 text-center text-sm text-stone-400">No data for this range.</p>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="fillActive" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLOR_ACTIVE} stopOpacity={0.28} />
                <stop offset="100%" stopColor={COLOR_ACTIVE} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="fillNew" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLOR_NEW} stopOpacity={0.18} />
                <stop offset="100%" stopColor={COLOR_NEW} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={{ stroke: "#e7eaf0" }} minTickGap={24} />
            <YAxis tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e7eaf0", boxShadow: "0 4px 16px rgba(18,24,38,0.08)" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
            <Area type="monotone" dataKey="activeUsers" name="Active users" stroke={COLOR_ACTIVE} strokeWidth={2.5} fill="url(#fillActive)" dot={false} activeDot={{ r: 4 }} />
            <Area type="monotone" dataKey="newUsers" name="New users" stroke={COLOR_NEW} strokeWidth={2} fill="url(#fillNew)" dot={false} activeDot={{ r: 4 }} />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/* Donut tooltip: a colour swatch, the category, its value and its share of the
   whole (e.g. "Organic Search: 1,234 (42.0%)"). */
function DonutTooltip({ active, payload, total }) {
  if (!active || !payload || !payload.length) return null;
  const slice = payload[0];
  const value = Number(slice.value) || 0;
  const pct = total > 0 ? ((value / total) * 100).toFixed(1) : "0.0";
  return (
    <div className="bg-white rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs text-stone-700 shadow-sm">
      <span className="inline-block h-2 w-2 rounded-full mr-1.5 align-middle" style={{ backgroundColor: slice.payload.fill }} />
      {slice.name}: <span className="font-semibold">{value.toLocaleString()}</span> ({pct}%)
    </div>
  );
}

// A blank/whitespace dimension value reads as "(not set)" (matches GA).
function cleanDimValue(v) {
  return v && String(v).trim() ? v : "(not set)";
}

// Join a row's dimension values into one label, each cleaned, with no dangling
// separators — "Organic Search / India / Edge / (not set)", never "… / /".
function joinDims(dimsValues) {
  const vals = (dimsValues || []).map(cleanDimValue);
  return vals.length ? vals.join(" / ") : "(not set)";
}

// Roughly how many characters fit on one Y-axis label line at the width/font
// below (~6.5px per char in the ~240px gutter, less a little padding).
const YAXIS_LABEL_WIDTH = 240;
const YAXIS_MAX_CHARS = 34;
const YAXIS_LINE_HEIGHT = 13;

// Greedily wrap `text` onto up to `maxLines` lines of ~`maxChars`, breaking on
// spaces (so the " / " separators wrap cleanly). Adds an ellipsis to the last
// line only if the text still overflows; hard-trims any single overlong word.
function wrapLabel(text, maxChars = YAXIS_MAX_CHARS, maxLines = 2) {
  const s = String(text).trim();
  if (!s) return ["(not set)"];
  const words = s.split(/\s+/);
  const lines = [];
  let current = "";
  let overflow = false;
  for (const w of words) {
    const candidate = current ? `${current} ${w}` : w;
    if (candidate.length <= maxChars || !current) {
      current = candidate;
    } else if (lines.length < maxLines - 1) {
      lines.push(current);
      current = w;
    } else {
      overflow = true; // more words than two lines can hold
      break;
    }
  }
  if (lines.length < maxLines && current) lines.push(current);

  if (overflow) {
    const last = lines[lines.length - 1] || "";
    lines[lines.length - 1] = `${last.slice(0, maxChars - 1).replace(/\s+$/, "")}…`;
  }
  // Hard-trim any line still too long (a single word with no break points).
  return lines.map((ln) => (ln.length > maxChars ? `${ln.slice(0, maxChars - 1)}…` : ln));
}

// Custom Y-axis tick: wraps the (possibly multi-dimension) category label onto
// up to 2 lines instead of truncating on one, so combined "A / B / C" labels
// stay readable. Block is vertically centred on the tick.
function WrappedYAxisTick({ x, y, payload }) {
  const lines = wrapLabel(payload?.value);
  const firstDy = -((lines.length - 1) * YAXIS_LINE_HEIGHT) / 2 + 4;
  return (
    <text x={x} y={y} textAnchor="end" fill="#78716c" fontSize={11}>
      {lines.map((ln, i) => (
        <tspan key={i} x={x} dy={i === 0 ? firstDy : YAXIS_LINE_HEIGHT}>
          {ln}
        </tspan>
      ))}
    </text>
  );
}

// Composition dimensions read best as a share-of-total donut (a few named
// categories). Time dimensions read best as a trend line. Everything else —
// and any multi-dimension report — uses the horizontal bar.
const COMPOSITION_DIMENSIONS = new Set([
  "sessionDefaultChannelGroup", "firstUserDefaultChannelGroup", "deviceCategory",
  "language", "platform", "operatingSystem", "continent", "newVsReturning", "userGender",
]);
const TIME_DIMENSIONS = new Set(DIMENSION_GROUPS["Time"].map(([, name]) => name));

/* Renders one combined report: a chart of the top rows by the FIRST selected
   metric on top, then a full-width table with one column per selected dimension
   + one per selected metric, plus a totals row. The chart type is chosen by the
   selected dimension when exactly ONE is selected — a donut for composition, a
   line for time series, a horizontal bar otherwise; multi-dimension reports
   always use the bar. table-fixed + a colgroup gives the metric columns a fixed
   width and lets the dimension columns take the rest and truncate (ellipsis +
   title), so long values never push columns off-screen — no horizontal scroll. */
function ReportResult({ report }) {
  const dims = report?.dimensions || [];
  const mets = report?.metrics || [];
  const rows = report?.rows || [];
  const totals = report?.totals || {};
  const firstMetric = mets[0];

  // Chart type by the single selected dimension (bar for 0 or many dimensions).
  const single = dims.length === 1 ? dims[0] : null;
  const chartType = !single
    ? "bar"
    : COMPOSITION_DIMENSIONS.has(single)
    ? "donut"
    : TIME_DIMENSIONS.has(single)
    ? "line"
    : "bar";

  // Bar: top 15 rows by the first metric; label = cleaned dims joined by " / "
  // (same label the table uses), wrapped onto 2 lines on the axis.
  const chartData = rows.slice(0, 15).map((r) => ({
    name: joinDims(r.dims),
    value: Number(r.metrics?.[firstMetric]) || 0,
  }));

  // Donut: top 6 categories by the first metric + an "Other" slice; total spans
  // ALL rows so the tooltip percentages are of the whole.
  const donutTotal = rows.reduce((s, r) => s + (Number(r.metrics?.[firstMetric]) || 0), 0);
  const donutTop = rows.slice(0, 6).map((r) => ({ name: joinDims(r.dims), value: Number(r.metrics?.[firstMetric]) || 0 }));
  const donutRest = rows.slice(6).reduce((s, r) => s + (Number(r.metrics?.[firstMetric]) || 0), 0);
  const donutData = donutRest > 0 ? [...donutTop, { name: "Other", value: donutRest }] : donutTop;

  // Line: every row in chronological order by the raw dimension value (GA date
  // strings sort chronologically); the "date" dimension shows as MM/DD.
  const lineData = rows
    .map((r) => ({ raw: String((r.dims || [])[0] ?? ""), value: Number(r.metrics?.[firstMetric]) || 0 }))
    .sort((a, b) => a.raw.localeCompare(b.raw))
    .map((d) => ({ name: single === "date" ? formatGADate(d.raw) : d.raw, value: d.value }));

  const colCount = dims.length + mets.length;

  return (
    <div className="space-y-4">
      {/* Chart of the first metric, matched to the dimension — on top */}
      <div className="bg-white rounded-xl border border-stone-200 p-4">
        {chartData.length === 0 ? (
          <p className="py-12 text-center text-sm text-stone-400">No data for this range.</p>
        ) : chartType === "donut" ? (
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={donutData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2} stroke="none">
                {donutData.map((d, i) => (
                  <Cell key={d.name} fill={d.name === "Other" ? "#a8a29e" : DONUT_COLORS[i % DONUT_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip content={<DonutTooltip total={donutTotal} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        ) : chartType === "line" ? (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={lineData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} minTickGap={24} />
              <YAxis tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={false} allowDecimals={false} width={40} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e7e5e4" }} />
              <Line type="monotone" dataKey="value" name={metricLabel(firstMetric)} stroke={COLOR_ACTIVE} strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 44)}>
            <BarChart data={chartData} layout="vertical" barCategoryGap="30%" margin={{ top: 4, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} />
              <YAxis
                type="category"
                dataKey="name"
                tickLine={false}
                axisLine={false}
                width={YAXIS_LABEL_WIDTH}
                interval={0}
                tick={<WrappedYAxisTick />}
              />
              <Tooltip cursor={{ fill: "#fafaf9" }} contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e7e5e4" }} />
              <Bar dataKey="value" name={metricLabel(firstMetric)} fill={COLOR_ACTIVE} radius={[0, 4, 4, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Combined table — one column per dimension + one per metric, + totals. */}
      <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
        <table className="w-full text-sm table-fixed">
          <colgroup>
            {dims.map((d) => (
              <col key={`d-${d}`} />
            ))}
            {mets.map((m) => (
              <col key={`m-${m}`} className="w-28" />
            ))}
          </colgroup>
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
              {dims.map((d) => (
                <th key={d} className="px-5 py-3 font-medium truncate" title={dimensionLabel(d)}>
                  {dimensionLabel(d)}
                </th>
              ))}
              {mets.map((m) => (
                <th key={m} className="px-5 py-3 font-medium truncate" title={metricLabel(m)}>
                  {metricLabel(m)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={colCount} className="px-5 py-8 text-center text-sm text-stone-400">
                  No data for this range.
                </td>
              </tr>
            ) : (
              rows.map((r, i) => (
                <tr key={i} className="hover:bg-stone-50">
                  {dims.map((d, di) => {
                    const v = cleanDimValue((r.dims || [])[di]);
                    return (
                      <td key={d} className="px-5 py-3 font-medium text-stone-800 truncate" title={v}>
                        {v}
                      </td>
                    );
                  })}
                  {mets.map((m) => (
                    <td key={m} className="px-5 py-3 font-data text-stone-700 whitespace-nowrap">
                      {formatMetric(m, r.metrics?.[m])}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-stone-200 bg-stone-50 font-semibold text-stone-900">
                <td colSpan={dims.length} className="px-5 py-3 uppercase text-xs tracking-wider text-stone-500">
                  Total
                </td>
                {mets.map((m) => (
                  <td key={m} className="px-5 py-3 font-data whitespace-nowrap">
                    {formatMetric(m, totals[m])}
                  </td>
                ))}
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   SEARCH CONSOLE (GSC) — per-project Google Search Console performance
   for a chosen date range, reusing the SAME service account as GA4. Its
   own date-range control sits at the top (default last 28 days), then the
   four headline cards (Total Clicks, Total Impressions, Average CTR, Avg
   Position), a clicks/impressions trend chart, and the Queries + Pages
   tables. Fed by GET /api/projects/:id/search-console. When the project
   has no GSC site URL — or the server returns {error} (no access, API not
   enabled, no data) — we show a friendly muted message instead of crashing.
   ════════════════════════════════════════════════════════════════════ */

// GSC CTR is a fraction (0–1) → one-decimal percentage; position is 1-based →
// one decimal; clicks/impressions are plain counts → locale-formatted integers.
function formatCtr(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`;
}
function formatPosition(value) {
  return (Number(value) || 0).toFixed(1);
}
function formatCount(value) {
  return (Number(value) || 0).toLocaleString();
}

// Raw GSC date "2026-06-01" → "06/01" for the trend chart axis/tooltip.
function formatGSCDate(raw) {
  if (!raw || raw.length !== 10) return raw || "";
  return `${raw.slice(5, 7)}/${raw.slice(8, 10)}`;
}

// ── Performance report config ─────────────────────────────────────────
// Search-type selector tabs: [label, API value]. Defaults to Web. (The API
// also accepts googleNews; we expose the five GSC surfaces the UI shows.)
const SC_SEARCH_TYPES = [
  ["Web", "web"],
  ["Image", "image"],
  ["Video", "video"],
  ["News", "news"],
  ["Discover", "discover"],
];

// Dimension tabs below the chart: [label, API dimension, table column header].
// Selecting a tab sets the active breakdown and refetches its rows.
const SC_DIMENSION_TABS = [
  ["Queries", "query", "Query"],
  ["Pages", "page", "Page"],
  ["Countries", "country", "Country"],
  ["Devices", "device", "Device"],
  ["Search appearance", "searchAppearance", "Search appearance"],
  ["Dates", "date", "Date"],
];

// Filter-bar dimensions: [label, API dimension]. (`date` isn't a filter
// dimension in GSC — only a breakdown — so it's intentionally absent here.)
const SC_FILTER_DIMENSIONS = [
  ["Query", "query"],
  ["Page", "page"],
  ["Country", "country"],
  ["Device", "device"],
  ["Search appearance", "searchAppearance"],
];

// Operators by dimension: Query & Page take the full text set; Country, Device
// and Search appearance only "is". [user-facing label, API operator] — the API
// names match the backend's SC_OPERATORS allowlist exactly.
const SC_TEXT_OPERATORS = [
  ["contains", "contains"],
  ["doesn't contain", "notContains"],
  ["exactly matches", "equals"],
  ["matches regex", "includingRegex"],
  ["doesn't match regex", "excludingRegex"],
];
const SC_IS_OPERATORS = [["is", "equals"]];

function scOperatorsFor(dimension) {
  return dimension === "query" || dimension === "page" ? SC_TEXT_OPERATORS : SC_IS_OPERATORS;
}

// Placeholder hint for a filter's value input, by dimension.
function scValuePlaceholder(dimension) {
  if (dimension === "country") return "3-letter code, e.g. ind, aus";
  if (dimension === "device") return "DESKTOP, MOBILE or TABLET";
  return "value";
}

// The table column header for an active breakdown dimension.
function scDimensionLabel(dimension) {
  const tab = SC_DIMENSION_TABS.find(([, name]) => name === dimension);
  return tab ? tab[2] : dimension;
}

// Filename-safe slug for an active dimension, from its tab label:
// query → "queries", searchAppearance → "search-appearance".
function scDimensionSlug(dimension) {
  const tab = SC_DIMENSION_TABS.find(([, name]) => name === dimension);
  return (tab ? tab[0] : dimension).toLowerCase().replace(/\s+/g, "-");
}

// One CSV field: wrap in double quotes and double any embedded quotes, so
// commas (in queries / page URLs / locale-formatted numbers) stay contained.
function csvField(value) {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

// The four toggleable metrics, in card/legend order, each with its plotting
// colour, chart Y-axis id and cell formatter. Clicks blue, Impressions purple,
// CTR green, Position orange (each line matches its card).
const SC_METRICS = [
  { key: "clicks", label: "Total Clicks", color: "#1a73e8", fmt: formatCount },
  { key: "impressions", label: "Total Impressions", color: "#7c3aed", fmt: formatCount },
  { key: "ctr", label: "Average CTR", color: "#16a34a", fmt: formatCtr },
  { key: "position", label: "Average Position", color: "#ea8600", fmt: formatPosition },
];

/* Chart tooltip: one colour-swatched line per plotted metric, each value
   formatted to its own kind (counts, CTR %, position to 1 dp). */
function SCChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-white rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs text-stone-700 shadow-sm">
      <p className="text-stone-400 mb-1">{label}</p>
      {payload.map((p) => {
        const m = SC_METRICS.find((x) => x.key === p.dataKey);
        return (
          <p key={p.dataKey} className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: p.color }} />
            {m ? m.label : p.name}: <span className="font-semibold">{m ? m.fmt(p.value) : p.value}</span>
          </p>
        );
      })}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════
   SEARCH CONSOLE (GSC) — a faithful replica of Google Search Console's
   Performance ("Search results") report. A search-type selector (Web /
   Image / Video / News / Discover) and the shared date-range control sit
   at the top; a stackable AND-joined filter bar follows. Below, four
   TOGGLEABLE metric cards (Clicks, Impressions, CTR, Position) drive a
   multi-axis time chart, then dimension tabs (Queries / Pages / Countries
   / Devices / Search appearance / Dates) each render a sortable breakdown
   table. Search type, date and filters all apply to the totals + chart +
   active table together, fed by POST /api/projects/:id/search-console/
   performance. When the project has no GSC site URL — or the server returns
   {error} — we show a friendly muted message instead of crashing.
   ════════════════════════════════════════════════════════════════════ */
function SearchConsoleTool({ project }) {
  const [range, setRange] = useState(() => presetRange(28)); // default: last 28 days
  const [activePreset, setActivePreset] = useState(28); // highlighted preset, or null
  const [searchType, setSearchType] = useState("web"); // Web by default
  const [filters, setFilters] = useState([]); // {dimension, operator, expression}
  const [dimension, setDimension] = useState("query"); // active table breakdown
  const [enabled, setEnabled] = useState(["clicks", "impressions"]); // plotted metrics
  const [data, setData] = useState(null); // null = first load
  const [error, setError] = useState(null); // transport/HTTP failure (api() threw)

  // No site URL set → friendly empty state, no fetch.
  const notConfigured = !project.gscSiteUrl;

  // Debounce the filter VALUE text so typing doesn't fire a request per
  // keystroke (~500ms). Structural changes (search type, date, dimension,
  // adding/removing rows, a row's dimension/operator) re-run immediately.
  const exprKey = filters.map((f) => f.expression).join(" ");
  const [debouncedExprKey, setDebouncedExprKey] = useState(exprKey);
  useEffect(() => {
    const t = setTimeout(() => setDebouncedExprKey(exprKey), 500);
    return () => clearTimeout(t);
  }, [exprKey]);

  const structuralKey = JSON.stringify(filters.map((f) => [f.dimension, f.operator]));

  useEffect(() => {
    if (notConfigured) return;
    let cancelled = false;
    // Keep the previous view on refetch (only the first load shows the big
    // loader) so switching tabs / typing filters doesn't blank the page.
    setError(null);
    // Drop half-built rows (no value yet) so we never send a contains "".
    const activeFilters = filters
      .filter((f) => f.expression.trim() !== "")
      .map((f) => ({ dimension: f.dimension, operator: f.operator, expression: f.expression }));
    api(`/projects/${project.id}/search-console/performance`, {
      method: "POST",
      body: { start: range.start, end: range.end, searchType, dimension, filters: activeFilters },
    })
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, range.start, range.end, searchType, dimension, structuralKey, debouncedExprKey, notConfigured]);

  const applyPreset = (days) => {
    setActivePreset(days);
    setRange(presetRange(days));
  };
  const applyCustom = (which, value) => {
    if (!value) return;
    setActivePreset(null);
    setRange((r) => ({ ...r, [which]: value }));
  };

  // ── Metric toggles (a card click shows/hides its line) ──
  const toggleMetric = (key) =>
    setEnabled((m) => (m.includes(key) ? m.filter((x) => x !== key) : [...m, key]));

  // ── Filter row helpers (stackable conditions combined with AND) ──
  const addFilter = () =>
    setFilters((f) => [...f, { dimension: "query", operator: "contains", expression: "" }]);
  const updateFilter = (i, patch) =>
    setFilters((f) =>
      f.map((row, idx) => {
        if (idx !== i) return row;
        const next = { ...row, ...patch };
        // When the dimension changes, snap the operator to one this dimension
        // actually offers (text dims → contains; "is"-only dims → equals).
        if (patch.dimension !== undefined) {
          const ops = scOperatorsFor(next.dimension).map(([, op]) => op);
          if (!ops.includes(next.operator)) next.operator = ops[0];
        }
        return next;
      })
    );
  const removeFilter = (i) => setFilters((f) => f.filter((_, idx) => idx !== i));

  // Clicking a dimension-table row applies that value as an "equals" filter on
  // the current tab's dimension — the GSC drill-down (click a query, switch to
  // Pages, see only that query's pages; stack more to narrow further). Uses the
  // RAW key the API returned (not a display value) so the filter matches, and
  // skips adding a duplicate of an identical {dimension, operator, expression}.
  const addFilterValue = (filterDimension, expression) =>
    setFilters((f) =>
      f.some(
        (x) => x.dimension === filterDimension && x.operator === "equals" && x.expression === expression
      )
        ? f
        : [...f, { dimension: filterDimension, operator: "equals", expression }]
    );

  // ── Export the active dimension table as CSV (client-side, no backend) ──
  // Builds the CSV from the loaded rows — the active tab's dimension column +
  // Clicks / Impressions / CTR / Avg Position, the same values the table shows
  // (with the current search type + date range + filters already applied since
  // `data` was fetched with them) — and triggers a download via a Blob + a
  // temporary anchor. Named gsc-<dimension>-<start>_<end>.csv.
  const exportCsv = () => {
    if (!data || data.error || !(data.rows && data.rows.length)) return;
    const header = [scDimensionLabel(data.dimension), "Clicks", "Impressions", "CTR", "Avg Position"];
    const lines = [header.map(csvField).join(",")];
    for (const r of data.rows) {
      lines.push(
        [
          r.key || "(not set)",
          formatCount(r.clicks),
          formatCount(r.impressions),
          formatCtr(r.ctr),
          formatPosition(r.position),
        ]
          .map(csvField)
          .join(",")
      );
    }
    const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `gsc-${scDimensionSlug(data.dimension)}-${range.start}_${range.end}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // The server reports no access / no data / a misconfigured property as
  // {error}; a thrown api() error lands in `error`. Either way we show the
  // same muted message in place of the data.
  const failed = error || data?.error;
  const trendData = (data?.trend || []).map((r) => ({ ...r, label: formatGSCDate(r.date) }));
  const plotted = SC_METRICS.filter((m) => enabled.includes(m.key));
  const canExport = !!data && !data.error && !!(data.rows && data.rows.length);

  return (
    <div className="w-full">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">Performance</h1>
        <p className="text-sm text-stone-500 mt-1">
          Google Search Console search results — clicks, impressions, CTR and average position, filterable by search type and dimension.
        </p>
      </div>

      {notConfigured ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <SearchCheck size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No Search Console data yet</h3>
          <p className="text-sm text-stone-500 mt-1 max-w-xs">
            Add this project&apos;s Search Console site URL to see search performance.
          </p>
        </div>
      ) : (
        <>
          {/* ── Search type + date range ── */}
          <div className="bg-white rounded-xl border border-stone-200 p-4 mb-4">
            {/* Search type selector */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-stone-400 mr-1">Search type</span>
              {SC_SEARCH_TYPES.map(([label, value]) => {
                const active = searchType === value;
                return (
                  <button
                    key={value}
                    onClick={() => setSearchType(value)}
                    aria-pressed={active}
                    className={`h-8 px-3 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 ${
                      active
                        ? "bg-orange-600 text-white border-orange-600"
                        : "bg-white text-stone-600 border-stone-300 hover:border-stone-400 hover:text-stone-800"
                    }`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            {/* Date presets */}
            <div className="flex flex-wrap items-center gap-2 border-t border-stone-100 pt-3">
              {RANGE_PRESETS.map((p) => {
                const active = activePreset === p.days;
                return (
                  <button
                    key={p.days}
                    onClick={() => applyPreset(p.days)}
                    aria-pressed={active}
                    className={`h-9 px-4 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 ${
                      active
                        ? "bg-orange-600 text-white border-orange-600"
                        : "bg-white text-stone-600 border-stone-300 hover:border-stone-400 hover:text-stone-800"
                    }`}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>

            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-stone-100 mt-3 pt-3 text-sm text-stone-500">
              <span className="font-medium text-stone-600">Custom range:</span>
              <span className="flex items-center gap-1.5">
                <span className="text-stone-400">From</span>
                <input
                  type="date"
                  value={range.start}
                  max={range.end}
                  onChange={(e) => applyCustom("start", e.target.value)}
                  aria-label="From date"
                  className={RANGE_FIELD_CLS}
                />
              </span>
              <span className="flex items-center gap-1.5">
                <span className="text-stone-400">To</span>
                <input
                  type="date"
                  value={range.end}
                  min={range.start}
                  onChange={(e) => applyCustom("end", e.target.value)}
                  aria-label="To date"
                  className={RANGE_FIELD_CLS}
                />
              </span>
            </div>

            <p className="text-xs text-stone-400 mt-3">
              Showing <span className="font-medium text-stone-600">{formatRangeLabel(range.start, range.end)}</span>
            </p>
          </div>

          {/* ── Filter bar — stackable conditions combined with AND ── */}
          <div className="bg-white rounded-xl border border-stone-200 p-4 mb-6">
            <div className="flex items-center justify-between gap-3 mb-2">
              <p className="text-xs font-semibold uppercase tracking-wider text-stone-400">Filters</p>
              <div className="flex items-center gap-2">
                {filters.length > 0 && (
                  <button
                    onClick={() => setFilters([])}
                    title="Remove all filters and show the full report"
                    className={`${BTN_GHOST} px-3 py-1.5 text-sm`}
                  >
                    <X size={14} /> Reset
                  </button>
                )}
                <button
                  onClick={exportCsv}
                  disabled={!canExport}
                  title="Download the current table as a CSV"
                  className={`${BTN_GHOST} px-3 py-1.5 text-sm disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  <Download size={14} /> Export
                </button>
              </div>
            </div>
            {filters.length > 0 && (
              <div className="space-y-2 mb-2">
                {filters.map((f, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    {i > 0 && (
                      <span className="text-xs font-semibold text-stone-400 px-1.5 py-0.5 rounded bg-stone-100">AND</span>
                    )}
                    <select
                      value={f.dimension}
                      onChange={(e) => updateFilter(i, { dimension: e.target.value })}
                      aria-label="Filter dimension"
                      className={`${RANGE_FIELD_CLS} w-auto`}
                    >
                      {SC_FILTER_DIMENSIONS.map(([label, name]) => (
                        <option key={name} value={name}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <select
                      value={f.operator}
                      onChange={(e) => updateFilter(i, { operator: e.target.value })}
                      aria-label="Filter operator"
                      className={`${RANGE_FIELD_CLS} w-auto`}
                    >
                      {scOperatorsFor(f.dimension).map(([label, op]) => (
                        <option key={op} value={op}>
                          {label}
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      value={f.expression}
                      onChange={(e) => updateFilter(i, { expression: e.target.value })}
                      placeholder={scValuePlaceholder(f.dimension)}
                      aria-label="Filter value"
                      className={`${RANGE_FIELD_CLS} flex-1 min-w-[10rem]`}
                    />
                    <button
                      onClick={() => removeFilter(i)}
                      aria-label="Remove filter"
                      className="p-1.5 rounded-md text-stone-300 hover:text-red-500 transition-colors"
                    >
                      <X size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={addFilter} className={`${BTN_GHOST} px-3 py-1.5 text-sm`}>
              <Plus size={14} /> Add filter
            </button>
          </div>

          {data === null && !error ? (
            <div className="flex justify-center py-16">
              <LoaderCircle size={22} className="text-orange-600 animate-spin" />
            </div>
          ) : failed ? (
            <div className="bg-white rounded-xl border border-stone-200 p-6">
              <p className="text-sm text-stone-400">
                Search Console isn&apos;t connected for this project yet, or there&apos;s no data for this search type, range and filters.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Toggleable metric cards — a click shows/hides that line. */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {SC_METRICS.map((m) => {
                  const on = enabled.includes(m.key);
                  return (
                    <button
                      key={m.key}
                      onClick={() => toggleMetric(m.key)}
                      aria-pressed={on}
                      title={on ? `Hide ${m.label} on the chart` : `Show ${m.label} on the chart`}
                      className="text-left rounded-xl border px-4 py-3 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-1"
                      style={
                        on
                          ? { backgroundColor: m.color, borderColor: m.color }
                          : { backgroundColor: "#fff", borderColor: "#e7e5e4" }
                      }
                    >
                      <p
                        className="text-xs uppercase tracking-wider"
                        style={{ color: on ? "rgba(255,255,255,0.85)" : "#a8a29e" }}
                      >
                        {m.label}
                      </p>
                      <p
                        className="text-2xl font-semibold mt-1 font-data"
                        style={{ color: on ? "#fff" : "#1c1917" }}
                      >
                        {m.fmt(data.totals?.[m.key])}
                      </p>
                    </button>
                  );
                })}
              </div>

              {/* Time chart — each enabled metric on its own scale (counts, CTR %,
                  position rank). The position axis is reversed so a better
                  (lower) position sits higher, matching GSC. */}
              <div className="bg-white rounded-xl border border-stone-200 p-4">
                {trendData.length === 0 || plotted.length === 0 ? (
                  <p className="py-12 text-center text-sm text-stone-400">
                    {plotted.length === 0 ? "Select a metric above to plot it." : "No data for this range."}
                  </p>
                ) : (
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={trendData} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#a8a29e" }} tickLine={false} axisLine={{ stroke: "#e7e5e4" }} minTickGap={24} />
                      {/* One hidden axis per metric so each has its own scale; the
                          position axis is reversed (lower = better = higher). */}
                      <YAxis yAxisId="clicks" hide allowDecimals={false} />
                      <YAxis yAxisId="impressions" hide allowDecimals={false} />
                      <YAxis yAxisId="ctr" hide domain={[0, "auto"]} />
                      <YAxis yAxisId="position" hide reversed domain={["auto", "auto"]} />
                      <Tooltip content={<SCChartTooltip />} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      {plotted.map((m) => (
                        <Line
                          key={m.key}
                          yAxisId={m.key}
                          type="monotone"
                          dataKey={m.key}
                          name={m.label}
                          stroke={m.color}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </div>

              {/* Dimension tabs + the active breakdown table. */}
              <div>
                <div className="flex flex-wrap gap-2 mb-3">
                  {SC_DIMENSION_TABS.map(([label, name]) => {
                    const active = dimension === name;
                    return (
                      <button
                        key={name}
                        onClick={() => setDimension(name)}
                        aria-pressed={active}
                        className={`h-8 px-3 text-sm font-medium rounded-lg border transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 ${
                          active
                            ? "bg-stone-900 text-white border-stone-900"
                            : "bg-white text-stone-600 border-stone-300 hover:border-stone-400 hover:text-stone-800"
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                <SearchConsoleRowsTable
                  label={scDimensionLabel(data.dimension)}
                  rows={data.rows || []}
                  onPick={data.dimension === "date" ? null : (key) => addFilterValue(data.dimension, key)}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* The active breakdown table: the dimension column + Clicks, Impressions, CTR,
   Avg Position, SORTABLE (click a header to re-sort; default Clicks desc).
   table-fixed + a colgroup pins the four metric columns at a fixed width
   (always visible, never wrap); the label column takes the rest and truncates
   with an ellipsis + title, so long queries/URLs never push columns
   off-screen. */
function SearchConsoleRowsTable({ label, rows, onPick }) {
  const [sort, setSort] = useState({ col: "clicks", dir: "desc" }); // default: Clicks desc

  // Click a header: same column → flip direction; new column → its default
  // (text key ascending, metrics descending).
  const sortBy = (col) =>
    setSort((s) =>
      s.col === col
        ? { col, dir: s.dir === "asc" ? "desc" : "asc" }
        : { col, dir: col === "key" ? "asc" : "desc" }
    );

  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.col];
    const bv = b[sort.col];
    const cmp =
      sort.col === "key"
        ? String(av ?? "").localeCompare(String(bv ?? ""))
        : (Number(av) || 0) - (Number(bv) || 0);
    return sort.dir === "asc" ? cmp : -cmp;
  });

  const cols = [
    { col: "key", head: label, metric: false },
    { col: "clicks", head: "Clicks", fmt: formatCount },
    { col: "impressions", head: "Impressions", fmt: formatCount },
    { col: "ctr", head: "CTR", fmt: formatCtr },
    { col: "position", head: "Avg. position", fmt: formatPosition },
  ];

  return (
    <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
      <table className="w-full text-sm table-fixed">
        <colgroup>
          <col />
          <col className="w-24" />
          <col className="w-28" />
          <col className="w-24" />
          <col className="w-28" />
        </colgroup>
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
            {cols.map((c) => {
              const active = sort.col === c.col;
              return (
                <th key={c.col} className="px-5 py-3 font-medium">
                  <button
                    onClick={() => sortBy(c.col)}
                    className={`inline-flex items-center gap-1 uppercase tracking-wider transition-colors hover:text-stone-600 ${
                      active ? "text-stone-700" : ""
                    } ${c.metric === false && c.col === "key" ? "" : "whitespace-nowrap"}`}
                  >
                    <span className={c.col === "key" ? "truncate" : ""}>{c.head}</span>
                    {active && (
                      <ChevronDown size={13} className={`shrink-0 transition-transform ${sort.dir === "asc" ? "rotate-180" : ""}`} />
                    )}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-stone-100">
          {sorted.length === 0 ? (
            <tr>
              <td colSpan={5} className="px-5 py-8 text-center text-sm text-stone-400">
                No data for this range.
              </td>
            </tr>
          ) : (
            sorted.map((r, i) => {
              const cell = r.key || "(not set)";
              return (
                <tr key={i} className="hover:bg-stone-50">
                  <td className="px-5 py-3 font-medium truncate" title={cell}>
                    {/* Clickable when the tab is a filterable dimension AND the row
                        has a real key — applies the RAW key as a filter (GSC drill-down). */}
                    {onPick && r.key ? (
                      <button
                        onClick={() => onPick(r.key)}
                        title={`Filter by ${label}: ${cell}`}
                        className="block w-full truncate text-left text-orange-700 hover:text-orange-800 hover:underline cursor-pointer"
                      >
                        {cell}
                      </button>
                    ) : (
                      <span className="text-stone-800">{cell}</span>
                    )}
                  </td>
                  <td className="px-5 py-3 font-data font-semibold text-stone-900 whitespace-nowrap">{formatCount(r.clicks)}</td>
                  <td className="px-5 py-3 font-data text-stone-600 whitespace-nowrap">{formatCount(r.impressions)}</td>
                  <td className="px-5 py-3 font-data text-stone-600 whitespace-nowrap">{formatCtr(r.ctr)}</td>
                  <td className="px-5 py-3 font-data text-stone-600 whitespace-nowrap">{formatPosition(r.position)}</td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

/* KPI card — premium analytics tile: a soft-purple icon chip, a colored
   comparison pill, the headline value, and an optional sparkline. Every
   prop beyond label/value is optional, so the simpler Rank Ledger stats
   (which pass only label + value, sometimes a `tone`) render cleanly too. */
function Stat({ label, value, tone, icon: Icon, delta, deltaDown, spark }) {
  const valueClass = tone === "up" ? "text-emerald-600" : tone === "down" ? "text-red-500" : "text-stone-900";
  return (
    <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-4 sm:p-5 flex flex-col rise-in">
      {(Icon || delta) && (
        <div className="flex items-center justify-between mb-3">
          {Icon ? (
            <span className="h-9 w-9 rounded-full bg-orange-50 text-orange-600 flex items-center justify-center shrink-0">
              <Icon size={17} />
            </span>
          ) : (
            <span />
          )}
          {delta != null && (
            <span
              className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-md ${
                deltaDown ? "text-red-600 bg-red-50" : "text-emerald-600 bg-emerald-50"
              }`}
            >
              {deltaDown ? <TrendingDown size={12} /> : <TrendingUp size={12} />}
              {delta}
            </span>
          )}
        </div>
      )}
      <p className={`text-2xl font-bold font-data tracking-tight ${valueClass}`}>{value}</p>
      <p className="text-xs font-medium text-stone-500 mt-0.5">{label}</p>
      {spark && spark.length > 1 && <Sparkline data={spark} down={deltaDown} />}
    </div>
  );
}

/* Dependency-free SVG sparkline — a soft area under a 2px line. Purple for an
   upward/neutral series, red when the card is flagged as declining. */
function Sparkline({ data, down }) {
  const w = 120;
  const h = 32;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const pts = data.map((v, i) => {
    const x = data.length === 1 ? w : (i / (data.length - 1)) * w;
    const y = h - 3 - ((v - min) / span) * (h - 6);
    return [x, y];
  });
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w} ${h} L0 ${h} Z`;
  const stroke = down ? "#dc2626" : "#5b5bf7";
  const fill = down ? "#fee2e2" : "#e3e3fd";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-8 mt-3 overflow-visible">
      <path d={area} fill={fill} opacity="0.55" />
      <path d={line} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* Green/red are reserved app-wide for exactly this: rank movement. */
function RankChange({ current, previous }) {
  if (current == null) return <span className="text-stone-300 font-data">—</span>;
  if (previous == null) {
    return (
      <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-sky-100 text-sky-700">
        New
      </span>
    );
  }
  const delta = previous - current;
  if (delta > 0) {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-600 font-semibold font-data">
        <TrendingUp size={14} /> +{delta}
      </span>
    );
  }
  if (delta < 0) {
    return (
      <span className="inline-flex items-center gap-1 text-red-500 font-semibold font-data">
        <TrendingDown size={14} /> {delta}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-stone-400 font-data">
      <Minus size={14} /> 0
    </span>
  );
}

function AddKeywordModal({ projectId, onClose, onAdded }) {
  const [term, setTerm] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = term.trim().length > 0;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${projectId}/keywords`, {
        method: "POST",
        body: { term: term.trim() },
      });
      onAdded();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Add keyword" onClose={onClose}>
      <p className="text-sm text-stone-500 mb-4">
        Track a new search term for this project. Its position fills in the next
        time you run a rank check (or record one by hand).
      </p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Keyword</label>
      <input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. restorative yoga near me"
        autoFocus
        className={INPUT_CLS}
      />

      <ErrorNote>{error}</ErrorNote>

      <button onClick={submit} disabled={!canSubmit || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Add keyword"}
      </button>
    </Modal>
  );
}
/* Records a new lookup: the server rotates current -> previous and
   stamps last_checked. Same write path a future rank-API job will use. */
function RecordRankModal({ projectId, keyword, onClose, onSaved }) {
  const [newRank, setNewRank] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const canSubmit = newRank !== "" && Number(newRank) >= 1;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/projects/${projectId}/keywords/${keyword.id}`, {
        method: "PATCH",
        body: { newRank: Number(newRank) },
      });
      onSaved();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  return (
    <Modal title="Record new rank" onClose={onClose}>
      <p className="text-sm text-stone-500 mb-4">
        New lookup for <span className="font-medium text-stone-800">{keyword.term}</span>. The current position{" "}
        <span className="font-data font-semibold text-stone-800">#{keyword.currentRank}</span> becomes "previous".
      </p>

      <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
        New rank
      </label>
      <input
        type="number"
        min="1"
        value={newRank}
        onChange={(e) => setNewRank(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder={`e.g. ${Math.max(1, keyword.currentRank - 2)}`}
        autoFocus
        className={INPUT_CLS}
      />

      <ErrorNote>{error}</ErrorNote>

      <button onClick={submit} disabled={!canSubmit || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : "Save lookup"}
      </button>
    </Modal>
  );
}

/* ════════════════════════════════════════════════════════════════════
   BULK IMPORT — download the sample, fill it, upload it.

   File uploads can't go through our normal api() helper (it sends
   JSON). The browser's FormData sends the file as multipart form data
   instead, with the auth token attached by hand. The server validates
   every row and returns a summary we display: how many imported, how
   many were duplicates, and a per-row reason for each rejected one.
   ════════════════════════════════════════════════════════════════════ */
function BulkImportModal({ projectId, onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    // Fetch with the auth header, then trigger a browser download from
    // the returned blob — you can't put headers on a plain <a href>.
    try {
      const res = await fetch("/api/projects/keywords/sample-template", {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("Couldn't download the template.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "rankboard-keywords-template.xlsx";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err.message);
    }
  };

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/projects/${projectId}/keywords/bulk-import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` }, // no Content-Type: the browser sets the multipart boundary
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Import failed.");
      setResult(data);
      onImported(); // refresh the ledger behind the modal
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Import keywords from Excel" onClose={onClose} wide>
      {!result ? (
        <>
          <ol className="text-sm text-stone-600 space-y-2 mb-4 list-decimal list-inside">
            <li>
              Download the template and fill in your keywords.{" "}
              <button onClick={downloadTemplate} className="text-orange-600 font-medium hover:underline inline-flex items-center gap-1">
                <Download size={13} /> Sample file
              </button>
            </li>
            <li>Keep the header row. One keyword per row.</li>
            <li>Upload the completed file below.</li>
          </ol>

          <label className="block">
            <span className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
              Excel file (.xlsx)
            </span>
            <input
              type="file"
              accept=".xlsx,.xlsm"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
              className="block w-full text-sm text-stone-600 file:mr-3 file:rounded-lg file:border-0 file:bg-stone-100 file:px-3 file:py-2 file:text-sm file:font-medium file:text-stone-700 hover:file:bg-stone-200 cursor-pointer"
            />
          </label>

          {file && (
            <p className="mt-2 text-xs text-stone-500 flex items-center gap-1.5">
              <FileSpreadsheet size={13} className="text-emerald-600" /> {file.name}
            </p>
          )}

          <ErrorNote>{error}</ErrorNote>

          <button onClick={upload} disabled={!file || busy} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
            {busy ? <LoaderCircle size={15} className="animate-spin" /> : <><Upload size={15} /> Import keywords</>}
          </button>
        </>
      ) : (
        <ImportResult result={result} onClose={onClose} />
      )}
    </Modal>
  );
}

function ImportResult({ result, onClose }) {
  const { imported, skippedExisting, errors } = result;
  return (
    <div>
      <div className="flex items-center gap-2 text-sm rounded-lg px-3 py-2 bg-emerald-50 border border-emerald-100 text-emerald-800">
        <Check size={15} />
        Imported {imported} keyword{imported === 1 ? "" : "s"}.
        {skippedExisting > 0 && ` ${skippedExisting} already existed and were skipped.`}
      </div>

      {errors.length > 0 && (
        <div className="mt-4">
          <p className="text-sm font-medium text-stone-700 mb-2">
            {errors.length} row{errors.length === 1 ? "" : "s"} skipped:
          </p>
          <div className="rounded-lg border border-stone-200 divide-y divide-stone-100 max-h-48 overflow-y-auto">
            {errors.map((e, i) => (
              <div key={i} className="px-3 py-2 text-xs flex gap-2">
                <span className="font-data text-stone-400 shrink-0">Row {e.row}</span>
                <span className="text-stone-600">{e.reason}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-stone-400 mt-2">Fix these rows in your file and import again — already-added keywords will be skipped.</p>
        </div>
      )}

      <button onClick={onClose} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
        Done
      </button>
    </div>
  );
}
