import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronLeft,
  CircleAlert,
  Clock,
  Eye,
  LoaderCircle,
  MailCheck,
  MousePointerClick,
  Paperclip,
  RefreshCw,
  Search,
  Send,
  X,
} from "lucide-react";
import { api } from "../api";
import { TopBar, ErrorNote, INPUT_CLS } from "../ui";


const STATUS_STYLES = {
  queued:       { label: "Queued",       cls: "bg-stone-100 text-stone-600" },
  outbox:       { label: "Dev outbox",   cls: "bg-stone-100 text-stone-500" },
  sent:         { label: "Sent",         cls: "bg-sky-100 text-sky-700" },
  deferred:     { label: "Deferred",     cls: "bg-amber-100 text-amber-700" },
  delivered:    { label: "Delivered",    cls: "bg-teal-100 text-teal-700" },
  opened:       { label: "Opened",       cls: "bg-emerald-100 text-emerald-700" },
  clicked:      { label: "Clicked",      cls: "bg-emerald-100 text-emerald-800" },
  bounced:      { label: "Bounced",      cls: "bg-red-100 text-red-700" },
  failed:       { label: "Failed",       cls: "bg-red-100 text-red-700" },
  complaint:    { label: "Spam report",  cls: "bg-rose-100 text-rose-700" },
  unsubscribed: { label: "Unsubscribed", cls: "bg-stone-200 text-stone-600" },
};

const STATUS_FILTERS = [
  "", "delivered", "opened", "clicked", "bounced", "failed", "complaint", "sent", "queued",
];

const CATEGORY_LABELS = {
  report: "Report",
  invite: "Invite",
  password_code: "Password code",
  login_code: "Sign-in code",
  other: "Other",
};

const RANGES = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "12 months" },
];

const PAGE_SIZE = 50;

/** Stored timestamps are UTC 'YYYY-MM-DD HH:MM:SS' with no offset — say so. */
const asDate = (s) => (s ? new Date(`${s.replace(" ", "T")}Z`) : null);

function formatWhen(s) {
  const d = asDate(s);
  if (!d || Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function formatFull(s) {
  const d = asDate(s);
  if (!d || Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    weekday: "short", day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function relative(s) {
  const d = asDate(s);
  if (!d || Number.isNaN(d.getTime())) return "";
  const mins = Math.round((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function StatusPill({ status }) {
  const s = STATUS_STYLES[status] || { label: status || "—", cls: "bg-stone-100 text-stone-600" };
  return (
    <span className={`inline-flex items-center text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${s.cls}`}>
      {s.label}
    </span>
  );
}

function StatCard({ icon: Icon, label, value, sub, tone = "stone" }) {
  const tones = {
    stone: "text-stone-400",
    emerald: "text-emerald-500",
    red: "text-red-500",
    sky: "text-sky-500",
  };
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-4 py-3.5">
      <div className="flex items-center gap-1.5 text-xs font-medium text-stone-400 uppercase tracking-wider">
        <Icon size={13} className={tones[tone]} />
        {label}
      </div>
      <p className="text-2xl font-bold text-stone-900 mt-1.5 font-display tabular-nums">{value}</p>
      <p className="text-xs text-stone-400 mt-0.5 min-h-[1rem]">{sub}</p>
    </div>
  );
}


function Sparkline({ series }) {
  if (!series?.length) return null;
  const peak = Math.max(...series.map((d) => d.sent), 1);
  return (
    <div className="bg-white rounded-xl border border-stone-200 px-4 py-3.5">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-stone-400 uppercase tracking-wider">Sent per day</span>
        <span className="flex items-center gap-3 text-xs text-stone-400">
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-sm bg-stone-300" /> sent</span>
          <span className="flex items-center gap-1"><i className="h-2 w-2 rounded-sm bg-emerald-400" /> opened</span>
        </span>
      </div>
      <div className="flex items-end gap-[3px] h-16 mt-3">
        {series.map((d) => (
          <div
            key={d.day}
            title={`${d.day} · ${d.sent} sent, ${d.opened} opened`}
            className="flex-1 min-w-[3px] relative bg-stone-200 rounded-sm hover:bg-stone-300 transition-colors"
            style={{ height: `${Math.max((d.sent / peak) * 100, 4)}%` }}
          >
            <div
              className="absolute bottom-0 inset-x-0 bg-emerald-400 rounded-sm"
              style={{ height: `${d.sent ? (d.opened / d.sent) * 100 : 0}%` }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

function TimelineRow({ event }) {
  const dot = {
    delivered: "bg-teal-400",
    opened: "bg-emerald-400",
    unique_opened: "bg-emerald-300",
    proxy_open: "bg-emerald-200",
    click: "bg-emerald-500",
    request: "bg-sky-400",
    deferred: "bg-amber-400",
  }[event.event] || "bg-red-400";

  return (
    <li className="relative pl-6 pb-4 last:pb-0">
      <span className="absolute left-0 top-1.5 h-2 w-2 rounded-full ring-4 ring-white" />
      <span className={`absolute left-0 top-1.5 h-2 w-2 rounded-full ${dot}`} />
      <span className="absolute left-[3px] top-4 bottom-0 w-px bg-stone-200 last:hidden" />
      <p className="text-sm font-medium text-stone-800 capitalize">
        {event.event.replace(/_/g, " ")}
      </p>
      <p className="text-xs text-stone-400 mt-0.5">{formatFull(event.at)}</p>
      {event.recipient && <p className="text-xs text-stone-500 font-data mt-0.5">{event.recipient}</p>}
      {event.reason && <p className="text-xs text-red-600 mt-1">{event.reason}</p>}
      {event.link && (
        <p className="text-xs text-stone-500 mt-1 break-all">
          <span className="text-stone-400">link: </span>{event.link}
        </p>
      )}
      {event.userAgent && <p className="text-[11px] text-stone-400 mt-1 truncate">{event.userAgent}</p>}
    </li>
  );
}

function DetailDrawer({ emailId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("timeline");

  useEffect(() => {
    let live = true;
    setDetail(null);
    setError(null);
    api(`/email-log/${emailId}`)
      .then((d) => live && setDetail(d))
      .catch((err) => live && setError(err.message));
    return () => {
      live = false;
    };
  }, [emailId]);

  // Escape closes. Without it the only way out is the X, which on a panel this
  // tall means scrolling back to the top first.
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(15, 23, 42, 0.35)" }}
        onClick={onClose}
      />
      <aside className="relative w-full max-w-xl bg-stone-50 h-full overflow-y-auto shadow-2xl">
        <header className="sticky top-0 bg-white/95 backdrop-blur border-b border-stone-200 px-6 py-4 flex items-start justify-between gap-4 z-10">
          <div className="min-w-0">
            <p className="text-xs text-stone-400 uppercase tracking-wider font-medium">Message</p>
            <h2 className="text-base font-bold text-stone-900 font-display truncate">
              {detail?.subject || "…"}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="p-1.5 rounded-md text-stone-400 hover:text-stone-700 hover:bg-stone-100 transition-colors shrink-0"
          >
            <X size={18} />
          </button>
        </header>

        {error && <div className="px-6"><ErrorNote>{error}</ErrorNote></div>}

        {!detail && !error && (
          <div className="py-24 flex justify-center">
            <LoaderCircle size={20} className="text-orange-600 animate-spin" />
          </div>
        )}

        {detail && (
          <div className="px-6 py-5 space-y-5">
            <div className="bg-white rounded-xl border border-stone-200 divide-y divide-stone-100">
              <Field label="Status">
                <span className="flex items-center gap-2 flex-wrap">
                  <StatusPill status={detail.status} />
                  {detail.openCount > 0 && (
                    <span className="text-xs text-stone-500">
                      {detail.openCount} open{detail.openCount === 1 ? "" : "s"}
                    </span>
                  )}
                  {detail.clickCount > 0 && (
                    <span className="text-xs text-stone-500">
                      {detail.clickCount} click{detail.clickCount === 1 ? "" : "s"}
                    </span>
                  )}
                </span>
              </Field>
              <Field label="To"><span className="font-data break-all">{detail.to}</span></Field>
              {detail.cc && <Field label="Cc"><span className="font-data break-all">{detail.cc}</span></Field>}
              <Field label="Sent">{formatFull(detail.sentAt)}</Field>
              {detail.deliveredAt && <Field label="Delivered">{formatFull(detail.deliveredAt)}</Field>}
              <Field label="First opened">
                {detail.firstOpenedAt ? formatFull(detail.firstOpenedAt) : (
                  <span className="text-stone-400">Not recorded</span>
                )}
              </Field>
           
            
              {detail.error && (
                <Field label="Problem"><span className="text-red-600">{detail.error}</span></Field>
              )}
              {detail.messageId && (
                <Field label="Provider ID">
                  <span className="font-data text-xs text-stone-400 break-all">{detail.messageId}</span>
                </Field>
              )}
            </div>

            <div>
              <div className="flex gap-1 mb-3">
                {["timeline", "message"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`text-sm font-medium px-3 py-1.5 rounded-lg capitalize transition-colors ${
                      tab === t
                        ? "bg-stone-900 text-white"
                        : "text-stone-500 hover:text-stone-800 hover:bg-stone-200"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>

              {tab === "timeline" ? (
                <div className="bg-white rounded-xl border border-stone-200 p-5">
                  {detail.events?.length ? (
                    <ul>{detail.events.map((e) => <TimelineRow key={e.id} event={e} />)}</ul>
                  ) : (
                    <p className="text-sm text-stone-400">
                      No provider events yet. Delivery and open events arrive from Brevo's
                      webhook — if nothing ever appears here, check that the webhook URL is
                      configured in Brevo.
                    </p>
                  )}
                </div>
              ) : (
                <div className="bg-white rounded-xl border border-stone-200 overflow-hidden">
                  {detail.html ? (
                   
                    <iframe
                      title="Email preview"
                      sandbox=""
                      srcDoc={detail.html}
                      className="w-full h-[28rem] bg-white"
                    />
                  ) : (
                    <pre className="p-5 text-sm text-stone-700 whitespace-pre-wrap font-sans">
                      {detail.body}
                    </pre>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div className="px-4 py-2.5 flex gap-4 text-sm">
      <span className="w-28 shrink-0 text-stone-400">{label}</span>
      <span className="text-stone-800 min-w-0">{children}</span>
    </div>
  );
}

export function EmailLogView({ user, onBack, onPeople, onLogout }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);
  // Stable identity: the drawer's Escape-key listener depends on it, and an
  // inline arrow here would tear that listener down and re-add it on every
  // render of this screen.
  const closeDrawer = useCallback(() => setOpenId(null), []);

  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [days, setDays] = useState(30);
  const [page, setPage] = useState(0);

  // Debounce the search box rather than firing a query per keystroke: this
  // table joins two tables and scans by ILIKE, so typing "anuranjan" unthrottled
  // is nine of those.
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search.trim());
      setPage(0);
    }, 250);
    return () => clearTimeout(t);
  }, [search]);

  const query = useMemo(() => {
    const p = new URLSearchParams({ days: String(days), limit: String(PAGE_SIZE) });
    if (q) p.set("q", q);
    if (status) p.set("status", status);
    if (category) p.set("category", category);
    return p;
  }, [q, status, category, days]);

  // Guards against an out-of-order response: a slow request for the previous
  // filter must not overwrite the results of the newer one behind it.
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    setRefreshing(true);
    try {
      const listQuery = new URLSearchParams(query);
      listQuery.set("offset", String(page * PAGE_SIZE));
      const [list, s] = await Promise.all([
        api(`/email-log?${listQuery}`),
        api(`/email-log/stats?${query}`),
      ]);
      if (seq !== requestSeq.current) return;
      setItems(list.items);
      setTotal(list.total);
      setStats(s);
      setError(null);
    } catch (err) {
      if (seq === requestSeq.current) setError(err.message);
    } finally {
      if (seq === requestSeq.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [query, page]);

  useEffect(() => {
    load();
  }, [load]);

  // Capped at 100. `opened` counts any message with a recorded open regardless
  // of what happened to it afterwards, while `delivered` excludes anything that
  // later bounced — so the raw ratio can top 100% on a small sample and read as
  // a bug. The cap is honest here because the number is already a lower bound.
  const openRate = stats?.delivered
    ? Math.min(100, Math.round((stats.opened / stats.delivered) * 100))
    : null;

  const pages = Math.ceil(total / PAGE_SIZE) || 1;

  // A Refresh (or a filter change racing one) can leave `page` past the end of
  // a shrunken result set. Without this the user sits on an empty page whose
  // Previous button has been unmounted along with the table.
  useEffect(() => {
    if (page > 0 && page >= pages) setPage(pages - 1);
  }, [page, pages]);

  return (
    <div className="min-h-screen bg-stone-100">
      <TopBar user={user} onLogout={onLogout} onHome={onBack} onPeople={onPeople} />

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8 sm:py-10">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-xs text-stone-500 hover:text-stone-800 mb-4 transition-colors"
        >
          <ChevronLeft size={14} /> Back to projects
        </button>

        <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">Email Log</h1>
            <p className="text-sm text-stone-500 mt-0.5">
              Every message this workspace has sent, and what happened to it after.
            </p>
          </div>
          <button
            onClick={load}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 hover:border-stone-400 bg-white text-stone-700 text-sm font-medium px-3 py-2 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={refreshing ? "animate-spin" : ""} /> Refresh
          </button>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatCard
            icon={Send}
            label="Sent"
            value={stats ? stats.total : "—"}
            sub={stats?.pending ? `${stats.pending} still in flight` : "in the selected period"}
            tone="sky"
          />
          <StatCard
            icon={MailCheck}
            label="Delivered"
            value={stats ? stats.delivered : "—"}
            sub={stats?.total ? `${Math.round((stats.delivered / stats.total) * 100)}% of sent` : ""}
          />
          <StatCard
            icon={Eye}
            label="Opened"
            value={stats ? stats.opened : "—"}
            sub={openRate === null ? "" : `${openRate}% of delivered · a floor, not a count`}
            tone="emerald"
          />
          <StatCard
            icon={CircleAlert}
            label="Problems"
            value={stats ? stats.failed : "—"}
            sub="bounced, blocked or marked spam"
            tone="red"
          />
        </div>

        <div className="mt-3">
          <Sparkline series={stats?.series} />
        </div>
{/* 
        <p className="text-xs text-stone-400 mt-3 leading-relaxed">
          Opens are counted from Brevo's tracking pixel. A recipient who blocks remote
          images never registers one, and Apple's Mail Privacy Protection loads it whether
          or not anyone read the message — so treat the open figure as a lower bound with
          noise on top, not a headcount. Delivery, bounces and clicks are exact.
        </p> */}

        <div className="flex flex-wrap items-center gap-2 mt-6">
          <div className="relative flex-1 min-w-[14rem]">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search recipient or subject…"
              className={`${INPUT_CLS} pl-9`}
            />
          </div>
          <select
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(0); }}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            {STATUS_FILTERS.map((s) => (
              <option key={s || "all"} value={s}>
                {s ? STATUS_STYLES[s]?.label || s : "Any status"}
              </option>
            ))}
          </select>
          <select
            value={category}
            onChange={(e) => { setCategory(e.target.value); setPage(0); }}
            className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-orange-500"
          >
            <option value="">Any kind</option>
            {Object.entries(CATEGORY_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
          <div className="flex rounded-lg border border-stone-300 bg-white overflow-hidden">
            {RANGES.map((r) => (
              <button
                key={r.days}
                onClick={() => { setDays(r.days); setPage(0); }}
                className={`px-2.5 py-2 text-sm font-medium transition-colors ${
                  days === r.days ? "bg-blue-900 primary ink  text-white" : "text-stone-600 hover:bg-stone-100"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>



        {loading ? (
          <div className="py-24 flex justify-center">
            <LoaderCircle size={22} className="text-orange-600 animate-spin" />
          </div>
        ) : (
          <>
            {items.length === 0 ? (
              <div className="bg-white rounded-xl border border-stone-200 py-20 text-center mt-4">
                <MailCheck size={26} className="mx-auto text-stone-300" />
                <p className="text-sm text-stone-500 mt-3">No emails match these filters.</p>
              </div>
            ) : (
            <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto mt-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
                    <th className="px-5 py-3 font-medium">Recipient</th>
                    <th className="px-5 py-3 font-medium">Subject</th>
                    <th className="px-5 py-3 font-medium">Status</th>
                    <th className="px-5 py-3 font-medium">Opened</th>
                    <th className="px-5 py-3 font-medium">Sent</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {items.map((m) => (
                    <tr
                      key={m.id}
                      onClick={() => setOpenId(m.id)}
                      className="hover:bg-stone-50 cursor-pointer"
                    >
                      <td className="px-5 py-3 max-w-[15rem]">
                        <span className="block font-medium text-stone-800 truncate font-data text-[13px]">
                          {m.to}
                        </span>
                        {m.cc && (
                          <span className="block text-xs text-stone-400 truncate">
                            +{m.cc.split(",").length} cc
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 max-w-[20rem]">
                        <span className="block text-stone-700 truncate">{m.subject}</span>
                        <span className="block text-xs text-stone-400 truncate">
                          {CATEGORY_LABELS[m.category] || m.category}
                          {m.projectName ? ` · ${m.projectName}` : ""}
                          {m.attachmentCount > 0 ? ` · ${m.attachmentCount} attachment` : ""}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <StatusPill status={m.status} />
                        {m.error && (
                          <span className="block text-xs text-red-500 mt-1 truncate max-w-[12rem]">
                            {m.error}
                          </span>
                        )}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap">
                        {m.firstOpenedAt ? (
                          <span className="text-stone-700">
                            {formatWhen(m.firstOpenedAt)}
                            <span className="flex items-center gap-2 text-xs text-stone-400 mt-0.5">
                              <span className="inline-flex items-center gap-1">
                                <Eye size={11} />{m.openCount}
                              </span>
                              {m.clickCount > 0 && (
                                <span className="inline-flex items-center gap-1">
                                  <MousePointerClick size={11} />{m.clickCount}
                                </span>
                              )}
                            </span>
                          </span>
                        ) : (
                          <span className="text-stone-300">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3 whitespace-nowrap text-stone-500">
                        {formatWhen(m.sentAt)}
                        <span className="flex items-center gap-1 text-xs text-stone-400 mt-0.5">
                          <Clock size={11} />{relative(m.sentAt)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            )}

            {/* Outside the empty branch on purpose: a filter that empties the
                current page must still leave a way back to the first one. */}
            <div className="flex items-center justify-between mt-4 text-sm text-stone-500">
              <span>
                {total === 0
                  ? "No results"
                  : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, total)} of ${total}`}
              </span>
              <span className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  className="px-3 py-1.5 rounded-lg border border-stone-300 bg-white hover:border-stone-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={page + 1 >= pages}
                  className="px-3 py-1.5 rounded-lg border border-stone-300 bg-white hover:border-stone-400 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Next
                </button>
              </span>
            </div>
          </>
        )}
      </main>

      {openId && <DetailDrawer emailId={openId} onClose={closeDrawer} />}
    </div>
  );
}
