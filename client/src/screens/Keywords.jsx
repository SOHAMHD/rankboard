import { useEffect, useMemo, useRef, useState } from "react";
import { ListOrdered, LoaderCircle, Plus, Save, Trash2 } from "lucide-react";
import { api } from "../api";
import { Modal, ErrorNote, can, INPUT_CLS, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function shortMonthLabel(key) {
  const [y, m] = String(key).split("-");
  const idx = Number(m) - 1;
  return idx >= 0 && idx < 12 ? `${MONTH_NAMES[idx].slice(0, 3)} ${y}` : String(key);
}

function recentMonths(count) {
  const out = [];
  const d = new Date();
  d.setDate(1);
  for (let i = 0; i < count; i++) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    d.setMonth(d.getMonth() - 1);
  }
  return out.reverse();
}

const MONTH_WINDOWS = [3, 6, 12];

export function KeywordsView({ user, project }) {
  const [monthCount, setMonthCount] = useState(3);
  const months = useMemo(() => recentMonths(monthCount), [monthCount]);

  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const [dirty, setDirty] = useState({});
  const dirtyCount = Object.keys(dirty).length;

  const toast = useToast();
  const canEdit = can(user, "recordRank");
  const canAdd = can(user, "addKeyword");
  const canDelete = can(user, "deleteKeyword");

  const load = async () => {
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/keyword-ranks?months=${months.join(",")}`);
      setRows(d.keywords);
      setDirty({});
    } catch (err) {
      setError(err.message);
      setRows([]);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, monthCount]);

  const cellKey = (id, month) => `${id}:${month}`;

  const cellValue = (row, month) => {
    const k = cellKey(row.id, month);
    if (k in dirty) return dirty[k];
    const v = row.ranks?.[month];
    return v === undefined || v === null ? "" : String(v);
  };

  const setCell = (row, month, raw) => {
    const clean = raw.replace(/[^0-9]/g, "");
    setDirty((d) => ({ ...d, [cellKey(row.id, month)]: clean }));
  };

  const save = async () => {
    if (!dirtyCount || saving) return;
    setSaving(true);
    setError(null);
    try {
      const cells = Object.entries(dirty).map(([k, v]) => {
        const [id, month] = k.split(":");
        return { keywordId: Number(id), month, rank: v === "" ? null : Number(v) };
      });
      const d = await api(`/projects/${project.id}/keyword-ranks`, { method: "PUT", body: { cells } });
      await load();
      toast.success(
        `Saved ${d.saved} rank${d.saved === 1 ? "" : "s"}` +
          (d.cleared ? `, cleared ${d.cleared}.` : ".")
      );
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  const removeKeyword = async (kw) => {
    try {
      await api(`/projects/${project.id}/keywords/${kw.id}`, { method: "DELETE" });
      setConfirmDelete(null);
      await load();
      toast.success(`Removed “${kw.term}”.`);
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    }
  };

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-stone-900 tracking-tight font-display">
            Keyword Rankings
            {!canEdit && (
              <span className="ml-2 align-middle text-xs font-medium px-2 py-0.5 rounded-full bg-stone-200 text-stone-600">
                View only
              </span>
            )}
          </h1>
          <p className="text-sm text-stone-500 mt-1">
            Enter each keyword&apos;s position per month. These are the numbers the report&apos;s
            three-month comparison uses.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={monthCount}
            onChange={(e) => setMonthCount(Number(e.target.value))}
            aria-label="Months to show"
            className={`${INPUT_CLS} w-auto`}
          >
            {MONTH_WINDOWS.map((n) => (
              <option key={n} value={n}>
                Last {n} months
              </option>
            ))}
          </select>
          {canAdd && (
            <button onClick={() => setShowAdd(true)} className={`${BTN_GHOST} px-4 py-2`}>
              <Plus size={15} /> Add keywords
            </button>
          )}
          {canEdit && (
            <button
              onClick={save}
              disabled={!dirtyCount || saving}
              title={dirtyCount ? `Save ${dirtyCount} changed cell(s)` : "No unsaved changes"}
              className={`${BTN_PRIMARY} px-4 py-2`}
            >
              {saving ? <LoaderCircle size={15} className="animate-spin" /> : <Save size={15} />}
              Save{dirtyCount ? ` (${dirtyCount})` : ""}
            </button>
          )}
        </div>
      </div>

      <ErrorNote>{error}</ErrorNote>

      {rows === null ? (
        <div className="flex justify-center py-16">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : rows.length === 0 ? (
        <div className="bg-white rounded-xl border border-dashed border-stone-300 py-16 flex flex-col items-center text-center px-6">
          <div className="h-12 w-12 rounded-full bg-stone-100 flex items-center justify-center mb-4">
            <ListOrdered size={20} className="text-stone-400" />
          </div>
          <h3 className="font-semibold text-stone-800 font-display">No keywords yet</h3>
          {canAdd ? (
            <>
              <p className="text-sm text-stone-500 mt-1 mb-5 max-w-xs">
                Add the keywords you track for this project, then fill in each month&apos;s position.
              </p>
              <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
                <Plus size={15} /> Add your first keywords
              </button>
            </>
          ) : (
            <p className="text-sm text-stone-500 mt-1 max-w-xs">
              The team hasn&apos;t added any keywords here yet.
            </p>
          )}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-stone-200 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wider text-stone-400 border-b border-stone-200">
                <th className="px-5 py-3 font-medium text-left sticky left-0 bg-white">Keyword</th>
                {months.map((m) => (
                  <th key={m} className="px-3 py-3 font-medium text-center whitespace-nowrap">
                    {shortMonthLabel(m)}
                  </th>
                ))}
                {canDelete && <th className="px-4 py-3 w-10" aria-label="Actions" />}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-stone-50">
                  <td
                    className="px-5 py-2 font-medium text-stone-800 max-w-[22rem] truncate sticky left-0 bg-white"
                    title={row.term}
                  >
                    {row.term}
                  </td>
                  {months.map((m) => {
                    const k = cellKey(row.id, m);
                    const isDirty = k in dirty;
                    return (
                      <td key={m} className="px-2 py-1.5 text-center">
                        <input
                          value={cellValue(row, m)}
                          onChange={(e) => setCell(row, m, e.target.value)}
                          disabled={!canEdit}
                          inputMode="numeric"
                          placeholder="—"
                          aria-label={`${row.term} rank for ${shortMonthLabel(m)}`}
                          className={`w-16 rounded-md border px-2 py-1 text-center text-sm font-data text-stone-900
                            focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500
                            disabled:bg-stone-50 disabled:text-stone-400 transition-colors
                            ${isDirty ? "border-orange-400 bg-orange-50" : "border-stone-200"}`}
                        />
                      </td>
                    );
                  })}
                  {canDelete && (
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => setConfirmDelete(row)}
                        aria-label={`Remove ${row.term}`}
                        title="Remove keyword"
                        className="p-1 rounded text-stone-300 hover:text-red-500 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {rows !== null && rows.length > 0 && canEdit && (
        <p className="text-xs text-stone-400 mt-3">
          Highlighted cells are unsaved. Clear a cell to remove that month&apos;s number — a blank
          shows as “—” in the report.
        </p>
      )}

      {showAdd && (
        <AddKeywordsModal
          projectId={project.id}
          onClose={() => setShowAdd(false)}
          onAdded={load}
        />
      )}

      {confirmDelete && (
        <Modal title={`Remove “${confirmDelete.term}”?`} onClose={() => setConfirmDelete(null)}>
          <p className="text-sm text-stone-600">
            This removes the keyword and every month&apos;s rank recorded for it. Reports already
            generated keep their own frozen copy and won&apos;t change.
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <button onClick={() => setConfirmDelete(null)} className={`${BTN_GHOST} px-4 py-2`}>
              Cancel
            </button>
            <button
              onClick={() => removeKeyword(confirmDelete)}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-red-700"
            >
              <Trash2 size={15} /> Remove
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function AddKeywordsModal({ projectId, onClose, onAdded }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const inputRef = useRef(null);

  const terms = text
    .split(/\r?\n/)
    .map((t) => t.trim())
    .filter(Boolean);

  const submit = async () => {
    if (!terms.length || busy) return;
    setBusy(true);
    setError(null);
    let added = 0;
    const failed = [];
    for (const term of terms) {
      try {
        await api(`/projects/${projectId}/keywords`, { method: "POST", body: { term } });
        added += 1;
      } catch {
        failed.push(term);
      }
    }
    setBusy(false);
    await onAdded();
    if (added) toast.success(`Added ${added} keyword${added === 1 ? "" : "s"}.`);
    if (failed.length) {
      setError(`Couldn't add ${failed.length}: ${failed.slice(0, 5).join(", ")}${failed.length > 5 ? "…" : ""}`);
      setText(failed.join("\n"));
    } else {
      onClose();
    }
  };

  return (
    <Modal title="Add keywords" onClose={onClose} wide>
      <p className="text-sm text-stone-500 mb-4">
        One keyword per line — paste a column straight from your sheet. Enter each month&apos;s
        position on the grid afterwards.
      </p>
      <textarea
        ref={inputRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        autoFocus
        placeholder={"electrical estimating\nelectrical estimators in perth\nelectrical takeoff services"}
        className={`${INPUT_CLS} font-data text-xs leading-relaxed resize-y`}
      />
      <ErrorNote>{error}</ErrorNote>
      <button onClick={submit} disabled={busy || !terms.length} className={`${BTN_PRIMARY} w-full mt-5 py-2.5`}>
        {busy ? (
          <LoaderCircle size={15} className="animate-spin" />
        ) : (
          <>
            <Plus size={15} /> Add {terms.length > 0 ? `${terms.length} keyword${terms.length === 1 ? "" : "s"}` : ""}
          </>
        )}
      </button>
    </Modal>
  );
}
