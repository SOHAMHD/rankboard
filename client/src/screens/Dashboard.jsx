import { Fragment, lazy, memo, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  Camera,
  Check,
  RefreshCw,
  Upload,
  FileSpreadsheet,
  Download,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FileText,
  Globe,
  Link2,
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
  KeyRound,
  Newspaper,
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
import { api, getToken, BASE } from "../api";
import { Modal, ErrorNote, ChangePasswordModal, can, isAuthor, isAdmin, isManager, INPUT_CLS, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";
import { MozOverview } from "./MozOverview";
import { BacklinksView } from "./Backlinks";
import { KeywordsView } from "./Keywords";
import { PostsView } from "./Posts";

const ReportsPanel = lazy(() =>
  import("./ReportEditor").then((m) => ({ default: m.ReportsPanel }))
);

const NAV_GROUPS = [
  {
    id: "traffic",
    label: "Traffic",
    icon: Globe,
    children: [
      { id: "traffic-overview", label: "Overview" },
      { id: "traffic-audience", label: "Audience" },
      { id: "traffic-technology", label: "Device / OS type" },
      { id: "traffic-pages", label: "Pages" },
    ],
  },
  {
    id: "keywords",
    label: "Keyword Rankings",
    icon: ListOrdered,
  },
  {
    id: "posts",
    label: "Posts",
    icon: Newspaper,
    children: [
      { id: "posts-blogs", label: "Blogs" },
      { id: "posts-linkedin", label: "LinkedIn Posts" },
    ],
  },
  {
    id: "backlinks",
    label: "Backlinks",
    icon: Link2,
  },
  {
    id: "search-console",
    label: "Search Console",
    icon: SearchCheck,
  },
  {
    id: "authority",
    label: "Authority",
    icon: ShieldCheck,
  },
];

const REPORTS_GROUP = { id: "reports", label: "Reports", icon: FileText };

function groupOf(navId) {
  return NAV_GROUPS.find((g) => (g.children || []).some((c) => c.id === navId));
}

const TrafficToolMemo = memo(TrafficTool);
const SearchConsoleToolMemo = memo(SearchConsoleTool);

export function ProjectDashboard({ user, projectId, onBack, onLogout }) {
  const [project, setProject] = useState(null);
  const [error, setError] = useState(null);
  const [activeNav, setActiveNav] = useState("traffic-overview");
  const [showPw, setShowPw] = useState(false);
  const [openGroups, setOpenGroups] = useState(() => {
    const g = groupOf("traffic-overview");
    return g ? [g.id] : [];
  });
  const toggleGroup = (id) =>
    setOpenGroups((open) => (open.includes(id) ? open.filter((x) => x !== id) : [...open, id]));

  const navGroups = useMemo(
    () => (isAuthor(user) ? [...NAV_GROUPS, REPORTS_GROUP] : NAV_GROUPS),
    [user]
  );

  const refresh = useCallback(async () => {
    try {
      const d = await api(`/projects/${projectId}`);
      setProject(d.project);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [projectId]);

  useEffect(() => {
    if (!isAuthor(user)) return;
    const warm = () => {
      import("./ReportEditor").catch(() => {});
    };
    if (typeof requestIdleCallback === "function") {
      const id = requestIdleCallback(warm, { timeout: 4000 });
      return () => cancelIdleCallback(id);
    }
    const t = setTimeout(warm, 2500);
    return () => clearTimeout(t);
  }, [user]);

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
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-64 bg-white border-r border-stone-200 flex-col">
        <div className="p-4 border-b border-stone-200">
          <button onClick={onBack} aria-label="Back to projects" title="Back to projects" className="block mb-4 cursor-pointer">
            <img src="/infapp-logo.png" alt="InfyApp" className="h-7 w-auto" />
          </button>
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

        <nav className="flex-1 p-3 overflow-y-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-2">SEO tools</p>
          {navGroups.map((group) => {
            const children = group.children || null;

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
            onClick={() => setShowPw(true)}
            aria-label="Change password"
            title="Change password"
            className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors shrink-0"
          >
            <KeyRound size={16} />
          </button>
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

      <div className="lg:hidden bg-white border-b border-stone-200 sticky top-0 z-20">
        <div className="px-4 pt-3 flex justify-center border-b border-stone-100">
          <button onClick={onBack} aria-label="Back to projects" title="Back to projects" className="cursor-pointer">
            <img src="/infapp-logo.png" alt="InfyApp" className="h-6 w-auto" />
          </button>
        </div>
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
          {navGroups.flatMap((group) =>
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

      {showPw && <ChangePasswordModal onClose={() => setShowPw(false)} />}
      <main className="px-6 py-6">
        {activeNav === "keywords" && <KeywordsView user={user} project={project} />}
        {activeNav === "backlinks" && <BacklinksView user={user} project={project} />}
        {activeNav === "posts-blogs" && <PostsView user={user} project={project} kind="blog" />}
        {activeNav === "posts-linkedin" && <PostsView user={user} project={project} kind="linkedin" />}
        {activeNav.startsWith("traffic-") && (
          <TrafficToolMemo project={project} view={activeNav.slice("traffic-".length)} />
        )}
        {activeNav === "search-console" && <SearchConsoleToolMemo project={project} />}
        {activeNav === "authority" && <MozOverview project={project} user={user} />}
        {activeNav === "reports" && isAuthor(user) && (
          <Suspense
            fallback={
              <div className="flex justify-center py-16">
                <LoaderCircle size={22} className="text-orange-600 animate-spin" />
              </div>
            }
          >
            <ReportsPanel user={user} project={project} />
          </Suspense>
        )}
      </main>
    </div>
  );
}

function groupByMonth(snapshots) {
  const order = [];
  const map = new Map();
  for (const s of snapshots) {
    if (!map.has(s.periodKey)) {
      map.set(s.periodKey, { periodKey: s.periodKey, label: s.label, snapshots: [] });
      order.push(s.periodKey);
    }
    map.get(s.periodKey).snapshots.push(s);
  }
  return order.map((k) => map.get(k));
}

function snapshotTimeLabel(iso) {
  if (!iso) return "—";
  const raw = String(iso);
  const d = new Date(raw.replace(" ", "T") + (raw.endsWith("Z") ? "" : "Z"));
  if (isNaN(d.getTime())) return raw;
  const date = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${date} · ${time}`;
}

function SnapshotMenu({ groups, selectedId, onSelect, onDownload }) {
  const [open, setOpen] = useState(false);
  const [openMonth, setOpenMonth] = useState(null);
  const [flip, setFlip] = useState(false);
  const rootRef = useRef(null);
  const closeTimer = useRef(null);

  const closeAll = () => {
    clearTimeout(closeTimer.current);
    setOpen(false);
    setOpenMonth(null);
  };

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) closeAll();
    };
    const onKey = (e) => e.key === "Escape" && closeAll();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => () => clearTimeout(closeTimer.current), []);

  const SUBMENU_W = 256;
  const openSubmenu = (periodKey) => {
    clearTimeout(closeTimer.current);
    const rect = rootRef.current?.getBoundingClientRect();
    if (rect) setFlip(rect.right + SUBMENU_W > window.innerWidth);
    setOpenMonth(periodKey);
  };
  const scheduleClose = () => {
    clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpenMonth(null), 150);
  };

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`${BTN_GHOST} px-4 py-2`}
      >
        <Camera size={15} /> Snapshots
        <ChevronDown size={14} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="absolute right-0 z-30 mt-1 w-56 rounded-xl border border-stone-200 bg-white shadow-lg py-1">
          {groups.map((g) => {
            const isOpen = openMonth === g.periodKey;
            return (
              <div
                key={g.periodKey}
                className="relative"
                onMouseEnter={() => openSubmenu(g.periodKey)}
                onMouseLeave={scheduleClose}
              >
                <button
                  className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-left transition-colors hover:bg-stone-50 ${
                    isOpen ? "bg-stone-50" : ""
                  }`}
                >
                  <span className="font-medium text-stone-800">{g.label}</span>
                  <span className="flex items-center gap-1.5 text-stone-400">
                    <span className="text-xs">{g.snapshots.length}</span>
                    <ChevronRight size={14} />
                  </span>
                </button>

                {isOpen && (
                  <div
                    onMouseEnter={() => clearTimeout(closeTimer.current)}
                    onMouseLeave={scheduleClose}
                    className={`absolute top-0 z-40 w-64 rounded-xl border border-stone-200 bg-white shadow-lg py-1 max-h-72 overflow-y-auto ${
                      flip ? "right-full mr-1" : "left-full ml-1"
                    }`}
                  >
                    {g.snapshots.map((s) => {
                      const active = s.id === selectedId;
                      return (
                        <div
                          key={s.id}
                          onClick={() => {
                            onSelect(s.id);
                            closeAll();
                          }}
                          className={`group flex items-center justify-between gap-2 px-3 py-2 text-sm cursor-pointer transition-colors hover:bg-stone-50 ${
                            active ? "bg-orange-50" : ""
                          }`}
                        >
                          <span className="flex items-center gap-2 min-w-0">
                            {active ? (
                              <Check size={14} className="text-orange-600 shrink-0" />
                            ) : (
                              <span className="w-3.5 shrink-0" />
                            )}
                            <span className={`truncate ${active ? "font-semibold text-orange-700" : "text-stone-700"}`}>
                              {snapshotTimeLabel(s.createdAt)}
                            </span>
                            <span className="text-xs text-stone-400 shrink-0 whitespace-nowrap">
                              {s.keywordCount} kw
                            </span>
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onDownload(s);
                            }}
                            title="Download this snapshot as CSV"
                            aria-label="Download snapshot as CSV"
                            className="p-1 rounded text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors shrink-0"
                          >
                            <Download size={14} />
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const VIEW_DEFAULT_DIMENSION = {
  overview: "sessionDefaultChannelGroup",
  audience: "country",
  technology: "deviceCategory",
  pages: "landingPagePlusQueryString",
};

const VIEW_DEFAULT_METRICS = {
  overview: ["activeUsers", "newUsers", "eventCount", "keyEvents", "averageEngagementTime"],
};

const DIMENSION_GROUPS = {
  "Geography": [["Country", "country"], ["Region", "region"], ["City", "city"], ["Continent", "continent"], ["Language", "language"]],
  "Traffic source (session)": [["Default Channel Group", "sessionDefaultChannelGroup"], ["Source", "sessionSource"], ["Medium", "sessionMedium"], ["Source / Medium", "sessionSourceMedium"], ["Campaign", "sessionCampaignName"]],
  "Traffic source (first user)": [["Default Channel Group", "firstUserDefaultChannelGroup"], ["Source", "firstUserSource"], ["Medium", "firstUserMedium"], ["Campaign", "firstUserCampaignName"]],
  "Platform / device": [["Device Category", "deviceCategory"], ["Operating System", "operatingSystem"], ["OS + Version", "operatingSystemWithVersion"], ["Browser", "browser"], ["Platform", "platform"], ["Screen Resolution", "screenResolution"], ["Device Model", "mobileDeviceModel"], ["Device Brand", "mobileDeviceBranding"]],
  "Page / screen": [["Landing Page", "landingPagePlusQueryString"], ["Page Path", "pagePath"], ["Page Path + Query", "pagePathPlusQueryString"], ["Page Title", "pageTitle"], ["Full Page URL", "fullPageUrl"], ["Hostname", "hostName"]],
  "Events": [["Event Name", "eventName"]],
  "User": [["New vs Returning", "newVsReturning"], ["Signed In With User ID", "signedInWithUserId"], ["Audience", "audienceName"]],
  "Time": [["Date", "date"], ["Date + Hour", "dateHour"], ["Hour", "hour"], ["Day of Week", "dayOfWeekName"], ["Week", "week"], ["Month", "month"], ["Year", "year"]],
  "Demographics (needs Google Signals)": [["Age", "userAgeBracket"], ["Gender", "userGender"], ["Interests", "brandingInterest"]],
};

const METRICS = {
  "Active Users": "activeUsers",
  "New Users": "newUsers",
  "Total Users": "totalUsers",
  "Sessions": "sessions",
  "Engaged Sessions": "engagedSessions",
  "Engagement Rate": "engagementRate",
  "Avg Session Duration": "averageSessionDuration",
  "User Engagement Duration": "userEngagementDuration",
  "Avg Engagement Time": "averageEngagementTime",
  "Views": "screenPageViews",
  "Event Count": "eventCount",
  "Bounce Rate": "bounceRate",
  "Key Events": "keyEvents",
  "Total Revenue": "totalRevenue",
  "Engaged Sessions / Active User": "engagedSessionsPerUser",
};

function dimensionLabel(apiName) {
  for (const items of Object.values(DIMENSION_GROUPS)) {
    for (const [label, name] of items) {
      if (name === apiName) return label;
    }
  }
  return apiName;
}

function metricLabel(apiName) {
  for (const [label, name] of Object.entries(METRICS)) {
    if (name === apiName) return label;
  }
  return apiName;
}

const METRIC_HELP = {
  activeUsers: "The number of distinct people who visited your site in the selected period.",
  newUsers: "People who visited your site for the very first time in this period.",
  totalUsers: "All unique visitors in this period — new and returning combined.",
  sessions: "Visits to your site. One session groups everything a user does within a single visit.",
  engagedSessions: "Sessions that lasted 10+ seconds, had a key event, or included 2 or more page views.",
  engagementRate: "The share of sessions that were engaged (engaged sessions ÷ total sessions).",
  averageSessionDuration: "The average length of a session, from first to last activity.",
  userEngagementDuration: "The total time users spent actively engaged with your site.",
  averageEngagementTime: "The average time your site was open and in focus per active user.",
  screenPageViews: "The total number of pages viewed, including repeat views of the same page.",
  eventCount: "The total number of events (page views, clicks, scrolls, etc.) that were triggered.",
  bounceRate: "The share of sessions that were NOT engaged — the opposite of engagement rate.",
  keyEvents: "How many times visitors completed actions you've marked as important (conversions).",
  totalRevenue: "Total revenue from purchases, subscriptions, and advertising.",
  engagedSessionsPerUser: "The average number of engaged sessions per active user.",
  clicks: "How many times people clicked through to your site from Google search results.",
  impressions: "How many times your site appeared in Google search results, whether clicked or not.",
  ctr: "Click-through rate — clicks ÷ impressions, shown as a percentage.",
  position: "Your site's average ranking position in search results (1 is the top; lower is better).",
};

function metricHelp(key) {
  return METRIC_HELP[key] || metricLabel(key);
}

const RATE_METRICS = new Set(["engagementRate", "bounceRate"]);
const DURATION_METRICS = new Set(["averageSessionDuration", "userEngagementDuration", "averageEngagementTime"]);

function formatMetric(name, value) {
  if (value == null) return "0";
  if (RATE_METRICS.has(name)) return `${(Number(value) * 100).toFixed(1)}%`;
  if (DURATION_METRICS.has(name)) return formatEngagement(value);
  if (name === "totalRevenue") {
    return `$${(Number(value) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (name === "engagedSessionsPerUser") return (Number(value) || 0).toFixed(2);
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString() : String(value);
}

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

const COLOR_ACTIVE = "#00A693";
const COLOR_NEW = "#5B5BF7";

const DONUT_COLORS = ["#5b5bf7", "#0284c7", "#f59e0b", "#7c3aed", "#0891b2", "#db2777", "#4f46e5", "#475569"];

function formatEngagement(seconds) {
  const total = Math.round(Number(seconds) || 0);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function toYMD(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function presetRange(days) {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - (days - 1));
  return { start: toYMD(start), end: toYMD(end) };
}

function parseYMD(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function formatRangeLabel(start, end) {
  const a = parseYMD(start);
  const b = parseYMD(end);
  const sameYear = a.getFullYear() === b.getFullYear();
  const left = `${MONTH_NAMES[a.getMonth()]} ${a.getDate()}${sameYear ? "" : `, ${a.getFullYear()}`}`;
  const right = `${MONTH_NAMES[b.getMonth()]} ${b.getDate()}, ${b.getFullYear()}`;
  return `${left} – ${right}`;
}

function formatGADate(raw) {
  if (!raw || raw.length !== 8) return raw || "";
  return `${raw.slice(4, 6)}/${raw.slice(6, 8)}`;
}

const RANGE_FIELD_CLS =
  "h-9 rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-900 focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-colors";

function TrafficTool({ project, view }) {
  const [range, setRange] = useState(() => presetRange(28));
  const [activePreset, setActivePreset] = useState(28);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const toast = useToast();

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

  useEffect(() => {
    if (data?.error) toast.error("We couldn't load traffic for this project. Check that the GA4 property ID is correct and that the SEO Dashboard service account has access to it.",
      { title: "Traffic" },[data?.error] );
  });

  const notConfigured = !project.gaPropertyId || (data && data.configured === false);

  const applyPreset = (days) => {
    setActivePreset(days);
    setRange(presetRange(days));
  };

  const applyMonth = (ym) => {
    if (!ym) return;
    const [y, m] = ym.split("-").map(Number);
    const lastDay = new Date(y, m, 0).getDate();
    setActivePreset(null);
    setRange({ start: `${ym}-01`, end: `${ym}-${String(lastDay).padStart(2, "0")}` });
  };

  const applyCustom = (which, value) => {
    if (!value) return;
    setActivePreset(null);
    setRange((r) => ({ ...r, [which]: value }));
  };

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
          <div className="bg-white rounded-xl border border-stone-200 p-4 mb-6">
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

            <p className="text-xs text-stone-400 mt-3">
              Showing <span className="font-medium text-stone-600">{formatRangeLabel(range.start, range.end)}</span>
            </p>
          </div>

          {view === "overview" &&
            (data === null ? (
              <div className="flex justify-center py-16">
                <LoaderCircle size={22} className="text-orange-600 animate-spin" />
              </div>
            ) : (
              (() => {
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

          <ExploreReport
            key={view}
            projectId={project.id}
            range={range}
            defaultDimension={VIEW_DEFAULT_DIMENSION[view]}
            defaultMetrics={VIEW_DEFAULT_METRICS[view]}
          />
        </>
      )}
    </div>
  );
}

function ExploreReport({ projectId, range, defaultDimension, defaultMetrics }) {
  const [dimensions, setDimensions] = useState([defaultDimension || "sessionDefaultChannelGroup"]);
  const [metrics, setMetrics] = useState(defaultMetrics || ["activeUsers", "newUsers"]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [runNonce, setRunNonce] = useState(0);
  const [openMenu, setOpenMenu] = useState(null);

  const dimsKey = dimensions.join(",");
  const metricsKey = metrics.join(",");

  useEffect(() => {
    let cancelled = false;
    setResult(null);
    setError(null);
    const reportMetrics = metrics.includes("sessions") ? metrics : [...metrics, "sessions"];
    api(`/projects/${projectId}/analytics/report`, {
      method: "POST",
      body: { start: range.start, end: range.end, dimensions, metrics: reportMetrics, filters: [], match: "AND", limit: 250 },
    })
      .then((d) => !cancelled && setResult(d.report))
      .catch((err) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, range.start, range.end, dimsKey, metricsKey, runNonce]);

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

  const failed = error || result?.error;
  const usesDemographics = dimensions.some((d) => DEMOGRAPHICS_NAMES.has(d));

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-stone-700 font-display">Explore</h2>
          <p className="text-xs text-stone-400 mt-0.5">
            Build a report from any dimensions and metrics — like GA4&apos;s Free-form exploration.
          </p>
        </div>
        <button onClick={() => setRunNonce((n) => n + 1)} title="Re-run the report now" className={`${BTN_PRIMARY} px-4 py-2`}>
          <RefreshCw size={15} /> Run
        </button>
      </div>

      <div className="bg-white rounded-xl border border-stone-200 p-4 mb-4 space-y-4">
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

      </div>

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
      ) : dimensions.includes(EVENT_DIMENSION) ? (
        <EventsReport projectId={projectId} range={range} runNonce={runNonce} />
      ) : (
        <ReportResult report={result} />
      )}
    </div>
  );
}

const EVENT_DIMENSION = "eventName";
const EVENT_METRICS = ["eventCount", "activeUsers", "newUsers", "sessions"];
const EVENT_CHANNEL_DIMENSION = "sessionDefaultChannelGroup";

function EventsReport({ projectId, range, runNonce }) {
  const [rows, setRows] = useState(null);
  const [byChannel, setByChannel] = useState({});
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    setError(null);
    setExpanded(null);

    const post = (dimensions, metrics) =>
      api(`/projects/${projectId}/analytics/report`, {
        method: "POST",
        body: { start: range.start, end: range.end, dimensions, metrics, filters: [], match: "AND", limit: 250 },
      });

    Promise.all([
      post([EVENT_DIMENSION], EVENT_METRICS),
      post([EVENT_DIMENSION, EVENT_CHANNEL_DIMENSION], ["eventCount"]).catch(() => null),
    ])
      .then(([main, split]) => {
        if (cancelled) return;
        if (main?.report?.error) return setError(main.report.error);

        const list = (main?.report?.rows || []).map((r) => ({
          name: (r.dims || [])[0] || "(not set)",
          eventCount: Number(r.metrics?.eventCount) || 0,
          activeUsers: Number(r.metrics?.activeUsers) || 0,
          newUsers: Number(r.metrics?.newUsers) || 0,
          sessions: Number(r.metrics?.sessions) || 0,
        }));
        list.sort((a, b) => b.eventCount - a.eventCount);
        setRows(list);

        const grouped = {};
        for (const r of split?.report?.rows || []) {
          const [ev, ch] = r.dims || [];
          if (!ev) continue;
          (grouped[ev] ||= []).push({ channel: cleanDimValue(ch), count: Number(r.metrics?.eventCount) || 0 });
        }
        for (const k of Object.keys(grouped)) grouped[k].sort((a, b) => b.count - a.count);
        setByChannel(grouped);
      })
      .catch((err) => !cancelled && setError(err.message));

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, range.start, range.end, runNonce]);

  const totalEvents = useMemo(() => (rows || []).reduce((s, r) => s + r.eventCount, 0), [rows]);

  if (error) {
    return (
      <div className="bg-white rounded-xl border border-stone-200 p-6">
        <p className="text-sm text-stone-400">{error}</p>
      </div>
    );
  }
  if (rows === null) {
    return (
      <div className="flex justify-center py-16">
        <LoaderCircle size={22} className="text-orange-600 animate-spin" />
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
        <div className="bg-white rounded-xl border border-stone-200 px-4 py-3">
          <p className="text-xs text-stone-400">Total events</p>
          <p className="text-xl font-semibold text-stone-900 font-data mt-0.5">{totalEvents.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border border-stone-200 px-4 py-3">
          <p className="text-xs text-stone-400">Event names</p>
          <p className="text-xl font-semibold text-stone-900 font-data mt-0.5">{rows.length.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border border-stone-200 px-4 py-3">
          <p className="text-xs text-stone-400">Most frequent</p>
          <p className="text-sm font-semibold text-stone-800 font-data mt-1.5 truncate" title={rows[0]?.name}>
            {rows[0]?.name || "—"}
          </p>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-stone-200">
          <h3 className="text-sm font-semibold text-stone-800 font-display">Events</h3>
          <span className="text-xs text-stone-400">{formatRangeLabel(range.start, range.end)}</span>
        </div>

        <table className="w-full text-sm table-fixed">
          <thead>
            <tr className="text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
              <th className="px-5 py-3 font-medium text-left w-[38%]">Event name</th>
              <th className="px-3 py-3 font-medium text-right w-[17%]">Event count</th>
              <th className="px-3 py-3 font-medium text-right w-[15%]">Active</th>
              <th className="px-3 py-3 font-medium text-right w-[15%]">New</th>
              <th className="px-5 py-3 font-medium text-right w-[15%]">Sessions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-sm text-stone-400">
                  No events for this range.
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const split = byChannel[r.name] || [];
                const open = expanded === r.name;
                return (
                  <Fragment key={r.name}>
                    <tr className="hover:bg-stone-50">
                      <td className="px-5 py-3">
                        <button
                          onClick={() => setExpanded(open ? null : r.name)}
                          disabled={split.length === 0}
                          title={split.length ? `${open ? "Hide" : "Show"} channel split for ${r.name}` : r.name}
                          className="flex w-full items-center gap-1.5 text-left font-data text-stone-800 disabled:cursor-default"
                        >
                          <ChevronDown
                            size={14}
                            className={`shrink-0 text-stone-300 transition-transform ${open ? "" : "-rotate-90"} ${
                              split.length === 0 ? "invisible" : ""
                            }`}
                          />
                          <span className="truncate">{r.name}</span>
                        </button>
                      </td>
                      <td className="px-3 py-3 text-right font-data font-medium text-stone-900">
                        {r.eventCount.toLocaleString()}
                      </td>
                      <td className="px-3 py-3 text-right font-data text-stone-700">{r.activeUsers.toLocaleString()}</td>
                      <td className="px-3 py-3 text-right font-data text-stone-700">
                        {r.newUsers > 0 ? r.newUsers.toLocaleString() : <span className="text-stone-300">—</span>}
                      </td>
                      <td className="px-5 py-3 text-right font-data text-stone-700">{r.sessions.toLocaleString()}</td>
                    </tr>
                    {open && (
                      <tr className="bg-stone-50">
                        <td colSpan={5} className="px-5 py-3">
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-2">
                            Event count by channel
                          </p>
                          <div className="space-y-1">
                            {split.map((s) => (
                              <div key={s.channel} className="flex items-center gap-3 text-xs">
                                <span className="w-40 shrink-0 truncate text-stone-500" title={s.channel}>
                                  {s.channel}
                                </span>
                                <span className="font-data text-stone-700">{s.count.toLocaleString()}</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
          {rows.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-stone-200 bg-stone-50 font-semibold text-stone-900">
                <td className="px-5 py-3 text-xs uppercase tracking-wider text-stone-500">Total</td>
                <td className="px-3 py-3 text-right font-data">{totalEvents.toLocaleString()}</td>
                <td colSpan={3} className="px-5 py-3 text-right text-xs font-normal text-stone-400">
                  User and session totals aren&apos;t additive across events
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

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

function TrafficTrendChart({ byDate }) {
  const rows = byDate.rows || [];
  const chartData = useMemo(
    () => rows.map((r) => ({ ...r, label: formatGADate(r.date) })),
    [rows]
  );

  return (
    <div className="bg-white rounded-xl border border-stone-200 shadow-sm p-4 sm:p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-sm font-semibold text-stone-900 font-display">Users over time</h2>
          <p className="text-xs text-stone-400 mt-0.5">Active vs. new users across the range</p>
        </div>

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

function cleanDimValue(v) {
  return v && String(v).trim() ? v : "(not set)";
}

function joinDims(dimsValues) {
  const vals = (dimsValues || []).map(cleanDimValue);
  return vals.length ? vals.join(" / ") : "(not set)";
}

const YAXIS_LABEL_WIDTH = 240;
const YAXIS_MAX_CHARS = 34;
const YAXIS_LINE_HEIGHT = 13;

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
      overflow = true;
      break;
    }
  }
  if (lines.length < maxLines && current) lines.push(current);

  if (overflow) {
    const last = lines[lines.length - 1] || "";
    lines[lines.length - 1] = `${last.slice(0, maxChars - 1).replace(/\s+$/, "")}…`;
  }
  return lines.map((ln) => (ln.length > maxChars ? `${ln.slice(0, maxChars - 1)}…` : ln));
}

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

const COMPOSITION_DIMENSIONS = new Set([
  "sessionDefaultChannelGroup", "firstUserDefaultChannelGroup", "deviceCategory",
  "language", "platform", "operatingSystem", "continent", "newVsReturning", "userGender",
]);
const TIME_DIMENSIONS = new Set(DIMENSION_GROUPS["Time"].map(([, name]) => name));

function ReportResult({ report, onDrill }) {
  const dims = report?.dimensions || [];
  const mets = report?.metrics || [];
  const rows = report?.rows || [];
  const totals = report?.totals || {};
  const firstMetric = mets[0];

  const single = dims.length === 1 ? dims[0] : null;
  const chartType = !single
    ? "bar"
    : COMPOSITION_DIMENSIONS.has(single)
    ? "donut"
    : TIME_DIMENSIONS.has(single)
    ? "line"
    : "bar";

  const { chartData, donutTotal, donutData, lineData } = useMemo(() => {
    const chartData = rows.slice(0, 15).map((r) => ({
      name: joinDims(r.dims),
      value: Number(r.metrics?.[firstMetric]) || 0,
    }));

    const donutTotal = rows.reduce((s, r) => s + (Number(r.metrics?.[firstMetric]) || 0), 0);
    const donutTop = rows.slice(0, 6).map((r) => ({ name: joinDims(r.dims), value: Number(r.metrics?.[firstMetric]) || 0 }));
    const donutRest = rows.slice(6).reduce((s, r) => s + (Number(r.metrics?.[firstMetric]) || 0), 0);
    const donutData = donutRest > 0 ? [...donutTop, { name: "Other", value: donutRest }] : donutTop;

    const lineData = rows
      .map((r) => ({ raw: String((r.dims || [])[0] ?? ""), value: Number(r.metrics?.[firstMetric]) || 0 }))
      .sort((a, b) => a.raw.localeCompare(b.raw))
      .map((d) => ({ name: single === "date" ? formatGADate(d.raw) : d.raw, value: d.value }));

    return { chartData, donutTotal, donutData, lineData };
  }, [rows, firstMetric, single]);

  const colCount = dims.length + mets.length;

  return (
    <div className="space-y-4">
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

      <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
              {dims.map((d) => (
                <th key={d} className="px-5 py-3 font-medium max-w-[16rem] truncate" title={dimensionLabel(d)}>
                  {dimensionLabel(d)}
                </th>
              ))}
              {mets.map((m) => (
                <th key={m} className="px-5 py-3 font-medium whitespace-nowrap" title={metricHelp(m)}>
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
                    const raw = (r.dims || [])[di];
                    const v = cleanDimValue(raw);
                    return (
                      <td key={d} className="px-5 py-3 font-medium text-stone-800 max-w-[16rem] truncate" title={v}>
                        {onDrill && raw && String(raw).trim() ? (
                          <button
                            onClick={() => onDrill(d, raw)}
                            title={`Filter by ${dimensionLabel(d)}: ${v}`}
                            className="block w-full truncate text-left text-orange-700 hover:text-orange-800 hover:underline cursor-pointer"
                          >
                            {v}
                          </button>
                        ) : (
                          v
                        )}
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

function formatCtr(value) {
  return `${((Number(value) || 0) * 100).toFixed(1)}%`;
}
function formatPosition(value) {
  return (Number(value) || 0).toFixed(1);
}
function formatCount(value) {
  return (Number(value) || 0).toLocaleString();
}

function formatGSCDate(raw) {
  if (!raw || raw.length !== 10) return raw || "";
  return `${raw.slice(5, 7)}/${raw.slice(8, 10)}`;
}

const SC_SEARCH_TYPES = [
  ["Web", "web"],
  ["Image", "image"],
  ["Video", "video"],
  ["News", "news"],
  ["Discover", "discover"],
];

const SC_DIMENSION_TABS = [
  ["Queries", "query", "Query"],
  ["Pages", "page", "Page"],
  ["Countries", "country", "Country"],
  ["Devices", "device", "Device"],
  ["Search appearance", "searchAppearance", "Search appearance"],
  ["Dates", "date", "Date"],
];

function scDimensionLabel(dimension) {
  const tab = SC_DIMENSION_TABS.find(([, name]) => name === dimension);
  return tab ? tab[2] : dimension;
}

function scDimensionSlug(dimension) {
  const tab = SC_DIMENSION_TABS.find(([, name]) => name === dimension);
  return (tab ? tab[0] : dimension).toLowerCase().replace(/\s+/g, "-");
}

function csvField(value) {
  let s = String(value ?? "");
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return `"${s.replace(/"/g, '""')}"`;
}

const SC_METRICS = [
  { key: "clicks", label: "Total Clicks", color: "#1a73e8", fmt: formatCount },
  { key: "impressions", label: "Total Impressions", color: "#7c3aed", fmt: formatCount },
  { key: "ctr", label: "Average CTR", color: "#16a34a", fmt: formatCtr },
  { key: "position", label: "Average Position", color: "#ea8600", fmt: formatPosition },
];

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

function SearchConsoleTool({ project }) {
  const [range, setRange] = useState(() => presetRange(28));
  const [activePreset, setActivePreset] = useState(28);
  const [searchType, setSearchType] = useState("web");
  const [filters, setFilters] = useState([]);
  const [dimension, setDimension] = useState("query");
  const [enabled, setEnabled] = useState(["clicks", "impressions"]);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pendingPick, setPendingPick] = useState(null);
  const toast = useToast();

  const notConfigured = !project.gscSiteUrl;

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
    setError(null);
    setBusy(true);
    const activeFilters = filters
      .filter((f) => f.expression.trim() !== "")
      .map((f) => ({ dimension: f.dimension, operator: f.operator, expression: f.expression }));
    api(`/projects/${project.id}/search-console/performance`, {
      method: "POST",
      body: { start: range.start, end: range.end, searchType, dimension, filters: activeFilters },
    })
      .then((d) => !cancelled && setData(d))
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => {
        if (!cancelled) {
          setBusy(false);
          setPendingPick(null);
        }
      });
    return () => {
      cancelled = true;
    };
    useEffect(() => {
  if (data?.error) toast.error("Google search console isn't configured for this project. Please check the project domain.", { title: "Search Console" });
}, [error.data?.error]);
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

  const toggleMetric = (key) =>
    setEnabled((m) => (m.includes(key) ? m.filter((x) => x !== key) : [...m, key]));

  const pickRow = (filterDimension, expression) => {
    setPendingPick(expression);
    addFilterValue(filterDimension, expression);
  };
  const addFilterValue = (filterDimension, expression) =>
    setFilters((f) =>
      f.some(
        (x) => x.dimension === filterDimension && x.operator === "equals" && x.expression === expression
      )
        ? f
        : [...f, { dimension: filterDimension, operator: "equals", expression }]
    );

  const selectDimension = (name) => {
    setDimension(name);
    setFilters((f) => f.filter((x) => !(x.dimension === name && x.operator === "equals")));
  };

  const failed = error || data?.error;
  const trendData = useMemo(
    () => (data?.trend || []).map((r) => ({ ...r, label: formatGSCDate(r.date) })),
    [data?.trend]
  );
  const plotted = useMemo(
    () => SC_METRICS.filter((m) => enabled.includes(m.key)),
    [enabled]
  );

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
          <div className="bg-white rounded-xl border border-stone-200 p-4 mb-4">
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

          {busy && data !== null && (
            <>
              <div className="fixed inset-x-0 top-0 z-50 h-1 overflow-hidden bg-orange-100">
                <div className="h-full w-2/5 animate-pulse rounded-r-full bg-orange-600" />
              </div>
              <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-full border border-stone-200 bg-white px-4 py-2 shadow-lg">
                <LoaderCircle size={16} className="animate-spin text-orange-600" />
                <span className="text-sm font-medium text-stone-600">Fetching Search Console data…</span>
              </div>
            </>
          )}

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
            <div
              className={`space-y-6 transition-opacity ${
                busy ? "pointer-events-none opacity-60" : ""
              }`}
              aria-busy={busy}
            >
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

              <div>
                <div className="flex flex-wrap gap-2 mb-3">
                  {SC_DIMENSION_TABS.map(([label, name]) => {
                    const active = dimension === name;
                    return (
                      <button
                        key={name}
                        onClick={() => selectDimension(name)}
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
                  onPick={data.dimension === "date" ? null : (key) => pickRow(data.dimension, key)}
                  pendingKey={busy ? pendingPick : null}
                />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SearchConsoleRowsTable({ label, rows, onPick, pendingKey }) {
  const [sort, setSort] = useState({ col: "clicks", dir: "desc" });

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
                <th
                  key={c.col}
                  className="px-5 py-3 font-medium"
                  title={c.col !== "key" ? metricHelp(c.col) : undefined}
                >
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
              const pending = pendingKey != null && r.key === pendingKey;
              return (
                <tr key={i} className={pending ? "bg-orange-50" : "hover:bg-stone-50"}>
                  <td className="px-5 py-3 font-medium truncate" title={cell}>
                    {onPick && r.key ? (
                      <button
                        onClick={() => onPick(r.key)}
                        disabled={pending}
                        title={pending ? `Loading ${cell}…` : `Filter by ${label}: ${cell}`}
                        className={`flex w-full items-center gap-2 truncate text-left ${
                          pending
                            ? "text-orange-800 cursor-wait"
                            : "text-orange-700 hover:text-orange-800 hover:underline cursor-pointer"
                        }`}
                      >
                        {pending && <LoaderCircle size={13} className="shrink-0 animate-spin" />}
                        <span className="truncate">{cell}</span>
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

function Stat({ label, value, tone, icon: Icon, delta, deltaDown, spark, onClick, active, title }) {
  const valueClass = tone === "up" ? "text-emerald-600" : tone === "down" ? "text-red-500" : "text-stone-900";
  const clickable = typeof onClick === "function";
  const Tag = clickable ? "button" : "div";
  const cls ="bg-white rounded-xl border shadow-sm p-4 sm:p-5 flex flex-col rise-in " +
    (active ? "border-orange-400 ring-2 ring-orange-500/30" : "border-stone-200") +
    (clickable
      ? " w-full text-left cursor-pointer hover:border-stone-300 hover:shadow transition-all focus:outline-none focus:ring-2 focus:ring-orange-500/40"
      : "");
  return (
    <Tag
      className={cls}
      {...(clickable ? { type: "button", onClick, "aria-pressed": active, title } : {})}
    >
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
    </Tag>
  );
}

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

function RankChange({ current, previous }) {
  if (current == null) return <span className="text-stone-300 font-data">—</span>;
  if (previous == null) {
    return (
      <span className="inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-sky-700">
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
  const toast = useToast();
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
      toast.success(`Added “${term.trim()}”.`, { title: "Keyword added" });
      onAdded();
    } catch (err) {
      setError(err.message);
      toast.error(err.message, { title: "Couldn't add keyword" });
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

function BulkImportModal({ projectId, onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const downloadTemplate = async () => {
    try {
      const res = await fetch(`${BASE}/api/projects/keywords/sample-template`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) throw new Error("Couldn't download the template.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "seo-dashboard-keywords-template.xlsx";
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
      const res = await fetch(`${BASE}/api/projects/${projectId}/keywords/bulk-import`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "Import failed.");
      setResult(data);
      onImported();
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
