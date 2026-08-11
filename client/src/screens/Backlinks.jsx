import { useEffect, useState } from "react";
import { AlertTriangle, ExternalLink, Link2, LoaderCircle, Plus, Trash2, Upload } from "lucide-react";
import { api } from "../api";
import { Modal, ErrorNote, isAuthor, INPUT_CLS, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function monthLabel(key) {
  const m = String(key).split("-");
  const idx = Number(m[1]) - 1;
  return m.length === 2 && idx >= 0 && idx < 12 ? `${MONTH_NAMES[idx]} ${m[0]}` : String(key);
}

function recentMonths(count = 24) {
  const out = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < count; i++) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}

export function BacklinksView({ user, project }) {
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState(null);
  const [monthFilter, setMonthFilter] = useState("all");
  const [showImport, setShowImport] = useState(false);
  const [confirmClear, setConfirmClear] = useState(null);
  const [clearing, setClearing] = useState(false);

  const author = isAuthor(user);
  const toast = useToast();

  const load = async () => {
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/backlinks`);
      setGroups(d.months);
    } catch (err) {
      setError(err.message);
      setGroups([]);
    }
  };

  useEffect(() => {
    load();
  }, [project.id]);

  const remove = async (id) => {
    try {
      await api(`/projects/${project.id}/backlinks/${id}`, { method: "DELETE" });
      await load();
      toast.success("Backlink removed.");
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    }
  };

  const clearMonth = async (group) => {
    setClearing(true);
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/backlinks/month/${group.month}`, {
        method: "DELETE",
      });
      if (monthFilter === group.month) setMonthFilter("all");
      await load();
      setConfirmClear(null);
      toast.success(
        `Deleted ${d.deleted} backlink${d.deleted === 1 ? "" : "s"} from ${group.label}.`
      );
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setClearing(false);
    }
  };

  const visible = groups && (monthFilter === "all" ? groups : groups.filter((g) => g.month === monthFilter));
  const total = groups ? groups.reduce((s, g) => s + g.count, 0) : 0;

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">
            Backlinks
            {!author && (
              <span className="ml-2 align-middle text-xs font-medium px-2 py-0.5 rounded-full bg-stone-200 text-stone-600">
                View only
              </span>
            )}
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            Backlink URLs the team tracks for this project, organised by month.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {groups && groups.length > 0 && (
            <select
              value={monthFilter}
              onChange={(e) => setMonthFilter(e.target.value)}
              aria-label="Filter by month"
              className={`${INPUT_CLS} w-auto`}
            >
              <option value="all">All months ({total})</option>
              {groups.map((g) => (
                <option key={g.month} value={g.month}>
                  {g.label} ({g.count})
                </option>
              ))}
            </select>
          )}
          {author && (
            <button onClick={() => setShowImport(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
              <Upload size={15} /> Import backlinks
            </button>
          )}
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {groups === null ? (
        <div className="flex justify-center py-16">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : groups.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <Link2 size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No backlinks yet</h3>
          {author ? (
            <>
              <p className="text-sm text-stone-500 mt-1 mb-5 max-w-xs">
                Pick a month and paste that month&apos;s backlink URLs to get started.
              </p>
              <button onClick={() => setShowImport(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
                <Plus size={15} /> Import your first batch
              </button>
            </>
          ) : (
            <p className="text-sm text-stone-500 mt-1 max-w-xs">The team hasn&apos;t added any backlinks here yet.</p>
          )}
        </div>
      ) : visible.length === 0 ? (
        <p className="text-sm text-stone-400 py-10 text-center">No backlinks for that month.</p>
      ) : (
        <div className="space-y-5">
          {visible.map((g) => (
            <div key={g.month} className="bg-white rounded-xl border border-stone-200 overflow-hidden">
              <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-stone-100">
                <h2 className="text-sm font-semibold text-stone-800 font-display">{g.label}</h2>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-500">
                    {g.count} link{g.count === 1 ? "" : "s"}
                  </span>
                  {author && g.count > 0 && (
                    <button
                      onClick={() => setConfirmClear(g)}
                      title={`Delete all ${g.count} backlinks in ${g.label}`}
                      className="inline-flex items-center gap-1 rounded-lg border border-stone-200 px-2.5 py-1 text-xs font-semibold text-stone-500 transition-colors hover:border-red-200 hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 size={13} /> Delete all
                    </button>
                  )}
                </div>
              </div>
              <ul className="divide-y divide-stone-100">
                {g.backlinks.map((b) => (
                  <li key={b.id} className="flex items-center gap-2 px-5 py-2.5 hover:bg-stone-50 group">
                    <Link2 size={14} className="text-stone-300 shrink-0" />
                    <a
                      href={/^https?:\/\//i.test(b.url) ? b.url : undefined}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={b.url}
                      className="text-sm text-stone-700 hover:text-orange-700 truncate flex-1 inline-flex items-center gap-1"
                    >
                      <span className="truncate">{b.url}</span>
                      <ExternalLink size={12} className="text-stone-300 shrink-0" />
                    </a>
                    {author && (
                      <button
                        onClick={() => remove(b.id)}
                        aria-label="Remove backlink"
                        title="Remove backlink"
                        className="p-1 rounded text-stone-300 hover:text-red-500 transition-colors shrink-0"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {showImport && (
        <BacklinkImportModal
          projectId={project.id}
          onClose={() => setShowImport(false)}
          onImported={load}
        />
      )}

      {confirmClear && (
        <Modal title={`Delete all backlinks in ${confirmClear.label}?`} onClose={() => setConfirmClear(null)}>
          <div className="flex items-start gap-3 rounded-lg border border-red-100 bg-red-50 px-3 py-2.5">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-500" />
            <p className="text-sm text-red-800">
              This permanently removes all{" "}
              <span className="font-semibold">{confirmClear.count}</span> backlink
              {confirmClear.count === 1 ? "" : "s"} saved for{" "}
              <span className="font-semibold">{confirmClear.label}</span>. It cannot be undone.
            </p>
          </div>
          <p className="mt-3 text-sm text-stone-500">
            Other months are not affected. You can re-import this month&apos;s batch at any time.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button onClick={() => setConfirmClear(null)} className={`${BTN_GHOST} px-4 py-2`}>
              Cancel
            </button>
            <button
              onClick={() => clearMonth(confirmClear)}
              disabled={clearing}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700 disabled:opacity-40"
            >
              {clearing ? <LoaderCircle size={15} className="animate-spin" /> : <Trash2 size={15} />}
              Yes, delete all
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function BacklinkImportModal({ projectId, onClose, onImported }) {
  const months = recentMonths();
  const [month, setMonth] = useState(months[0]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const toast = useToast();

  const lineCount = text.split(/\r?\n/).filter((l) => l.trim()).length;

  const submit = async () => {
    if (!month) {
      setError("Pick the month this batch belongs to.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const urls = text.split(/\r?\n/);
      const d = await api(`/projects/${projectId}/backlinks/import`, {
        method: "POST",
        body: { month, urls },
      });
      setResult(d);
      onImported();
      toast.success(
        `Added ${d.added} backlink${d.added === 1 ? "" : "s"} to ${monthLabel(d.month)}.`
      );
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Import backlinks" onClose={onClose} wide>
      {!result ? (
        <>
          <p className="text-sm text-stone-500 mb-4">
            Choose the month this batch belongs to, then paste the backlink URLs — one per
            line (copy the month&apos;s column straight out of your sheet). Duplicates already
            saved for that month are skipped.
          </p>

          <label htmlFor="backlink-import-month" className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">
            Month
          </label>
          {/* A month input emits exactly the "YYYY-MM" the API already expects, so
              no conversion is needed. It also lifts the 24-month cap the old
              dropdown imposed, which mattered for back-filling older batches.
              `max` stops a future month being picked — backlinks can't predate
              their own acquisition. */}
          <input
            id="backlink-import-month"
            type="month"
            value={month}
            max={months[0]}
            onChange={(e) => setMonth(e.target.value)}
            className={INPUT_CLS}
          />
          {month && (
            <p className="text-[11px] text-stone-400 mt-1">{monthLabel(month)}</p>
          )}

          <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5 mt-4">
            Backlink URLs (one per line)
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={10}
            autoFocus
            placeholder={"https://example.com/a\nhttps://another-site.com/post"}
            className={`${INPUT_CLS} font-data text-xs leading-relaxed resize-y`}
          />

          <ErrorNote>{error}</ErrorNote>

          {/* A month input can be cleared, which a select never could — so the
              month is now part of what makes the form valid. */}
          <button
            onClick={submit}
            disabled={busy || lineCount === 0 || !month}
            className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}
          >
            {busy ? (
              <LoaderCircle size={15} className="animate-spin" />
            ) : (
              <>
                <Upload size={15} /> Import {lineCount > 0 ? `${lineCount} line${lineCount === 1 ? "" : "s"}` : ""} to {monthLabel(month)}
              </>
            )}
          </button>
        </>
      ) : (
        <div>
          <div className="flex items-start gap-2 text-sm rounded-lg px-3 py-2 bg-emerald-50 border border-emerald-100 text-emerald-800">
            <span>
              Added {result.added} backlink{result.added === 1 ? "" : "s"} to {monthLabel(result.month)}.
              {result.skipped > 0 && ` ${result.skipped} duplicate${result.skipped === 1 ? "" : "s"} skipped.`}
            </span>
          </div>
          <div className="flex gap-2 mt-5">
            <button
              onClick={() => {
                setResult(null);
                setText("");
              }}
              className={`${BTN_GHOST} flex-1 py-2.5`}
            >
              Import more
            </button>
            <button onClick={onClose} className={`${BTN_PRIMARY} flex-1 py-2.5`}>
              Done
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
