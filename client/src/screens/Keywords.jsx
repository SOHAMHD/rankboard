import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  Download,
  FileSpreadsheet,
  ListOrdered,
  LoaderCircle,
  Plus,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { api, getToken, BASE } from "../api";
import { Modal, ErrorNote, can, INPUT_CLS, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

//: Mirrors keyword_rank_service.MAX_RANK. The input's maxLength keeps a leaned-on
//: digit key from producing a value the INTEGER column can't hold.
const MAX_RANK = 1000;
const MAX_RANK_DIGITS = String(MAX_RANK).length;

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

/**
 * One table row. memo'd on its own slice of the dirty map, so typing in one cell
 * re-renders only that row instead of every controlled input in the grid.
 */
const KeywordRow = memo(function KeywordRow({
  row,
  months,
  rowDirty,
  canEdit,
  canDelete,
  onCell,
  onDelete,
}) {
  const valueFor = (month) => {
    if (rowDirty && month in rowDirty) return rowDirty[month];
    const v = row.ranks?.[month];
    return v === undefined || v === null ? "" : String(v);
  };

  return (
    <tr className="hover:bg-stone-50">
      <td
        className="px-5 py-2 font-medium text-stone-800 max-w-[22rem] truncate sticky left-0 bg-white"
        title={row.term}
      >
        {row.term}
      </td>
      {months.map((m) => {
        const isDirty = Boolean(rowDirty && m in rowDirty);
        return (
          <td key={m} className="px-2 py-1.5 text-center">
            <input
              value={valueFor(m)}
              onChange={(e) => onCell(row, m, e.target.value)}
              disabled={!canEdit}
              inputMode="numeric"
              maxLength={MAX_RANK_DIGITS}
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
            onClick={() => onDelete(row)}
            aria-label={`Remove ${row.term}`}
            title="Remove keyword"
            className="p-1 rounded text-stone-500 hover:text-red-500 transition-colors"
          >
            <Trash2 size={14} />
          </button>
        </td>
      )}
    </tr>
  );
});

export function KeywordsView({ user, project, unsavedRef }) {
  const [monthCount, setMonthCount] = useState(3);
  const months = useMemo(() => recentMonths(monthCount), [monthCount]);

  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);

  const [dirty, setDirty] = useState({});
  const dirtyCount = Object.keys(dirty).length;

  const toast = useToast();
  const canEdit = can(user, "recordRank");
  const canAdd = can(user, "addKeyword");
  const canDelete = can(user, "deleteKeyword");

  // `keepEdits` is for the conflict case: pull in the current numbers so the
  // next save is checked against them, without throwing away what the user
  // typed. A plain load() clears the pending edits.
  // Bumped per request so a slow response for a window the user has already
  // moved away from can't land last and repopulate the grid for the wrong months.
  // Every other fetch in the codebase guards this; this one was the outlier.
  const loadSeq = useRef(0);

  const load = async ({ keepEdits = false } = {}) => {
    const seq = ++loadSeq.current;
    setError(null);
    try {
      const d = await api(`/projects/${project.id}/keyword-ranks?months=${months.join(",")}`);
      if (seq !== loadSeq.current) return false;
      setRows(d.keywords);
      if (!keepEdits) setDirty({});
      return true;
    } catch (err) {
      if (seq !== loadSeq.current) return false;
      setError(err.message);
      if (!keepEdits) setRows([]);
      return false;
    }
  };

  useEffect(() => {
    load();
    // Invalidate any in-flight request on unmount or a window change, so nothing
    // writes state after this screen has gone.
    return () => { loadSeq.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id, monthCount]);

  // Report the unsaved count upward so the dashboard can guard the exits it owns
  // — switching tabs and going back to the projects list both unmount this grid,
  // and React discards the edits without asking. A ref rather than a callback
  // prop so a keystroke here doesn't re-render the whole dashboard.
  useEffect(() => {
    if (!unsavedRef) return undefined;
    unsavedRef.current = () => dirtyCount;
    return () => { unsavedRef.current = null; };
  }, [unsavedRef, dirtyCount]);

  // Closing the tab or hitting back used to take unsaved cells with it silently.
  // The browser's own prompt is the only thing that can interrupt those.
  useEffect(() => {
    if (!dirtyCount) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirtyCount]);

  // Changing the window reloads the grid, and the reload clears `dirty` — so
  // without this the selector quietly threw away whatever was typed.
  const changeMonthCount = (next) => {
    if (next === monthCount) return;
    if (
      dirtyCount &&
      !window.confirm(
        `You have ${dirtyCount} unsaved change${dirtyCount === 1 ? "" : "s"}. ` +
          "Changing the date range will discard them. Continue?"
      )
    ) {
      return;
    }
    setMonthCount(next);
  };

  // `dirty` is a flat "<id>:<month>" map, which every cell had to consult — so a
  // single keystroke changed a value every row depended on and React reconciled
  // all of them (12 months x 150 keywords = 1800 controlled inputs). Regrouping
  // it per row means only the edited row's prop identity changes, and the memo on
  // KeywordRow stops the rest from re-rendering at all.
  const dirtyByRow = useMemo(() => {
    const out = {};
    for (const [k, v] of Object.entries(dirty)) {
      const sep = k.indexOf(":");
      const id = k.slice(0, sep);
      (out[id] || (out[id] = {}))[k.slice(sep + 1)] = v;
    }
    return out;
  }, [dirty]);

  // Stable identity so KeywordRow's memo isn't defeated by a new handler each render.
  const setCell = useCallback((row, month, raw) => {
    const clean = raw.replace(/[^0-9]/g, "").slice(0, MAX_RANK_DIGITS);
    setDirty((d) => ({ ...d, [`${row.id}:${month}`]: clean }));
  }, []);

  // What the grid last loaded for a cell — sent as `expected` so the server can
  // reject a save that would overwrite someone else's edit.
  const loadedValue = useCallback(
    (keywordId, month) => {
      const row = (rows || []).find((r) => String(r.id) === String(keywordId));
      const v = row?.ranks?.[month];
      return v === undefined || v === null ? null : v;
    },
    [rows]
  );

  const save = async () => {
    if (!dirtyCount || saving) return;
    setSaving(true);
    setError(null);
    try {
      const cells = Object.entries(dirty).map(([k, v]) => {
        const [id, month] = k.split(":");
        const rank = v === "" ? null : Number(v);
        return {
          keywordId: Number(id),
          month,
          rank,
          expected: loadedValue(id, month),
        };
      });
      const tooBig = cells.find((c) => c.rank !== null && c.rank > MAX_RANK);
      if (tooBig) {
        throw new Error(`Rank must be ${MAX_RANK} or lower — check ${tooBig.month}.`);
      }
      const d = await api(`/projects/${project.id}/keyword-ranks`, {
        method: "PUT",
        body: { cells, checkConflicts: true },
      });
      await load();
      toast.success(
        `Saved ${d.saved} rank${d.saved === 1 ? "" : "s"}` +
          (d.cleared ? `, cleared ${d.cleared}.` : ".")
      );
    } catch (err) {
      if (err.status === 409) {
        // Someone else moved the same cells. Pull in their numbers so the retry
        // is checked against what's actually stored, but keep the pending edits
        // — the highlighted cells still show what this user typed, and saving
        // again now applies them on top, knowingly.
        await load({ keepEdits: true });
        setError(
          `${err.message} The grid below now shows the current numbers; your unsaved ` +
            "cells are still highlighted. Save again to apply them over the top."
        );
        toast.error(err.message, { title: "Save conflict" });
      } else {
        setError(err.message);
        toast.error(err.message);
      }
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
            onChange={(e) => changeMonthCount(Number(e.target.value))}
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
            <>
              <button onClick={() => setShowImport(true)} className={`${BTN_GHOST} px-4 py-2`}>
                <FileSpreadsheet size={15} /> Import from Excel
              </button>
              <button onClick={() => setShowAdd(true)} className={`${BTN_GHOST} px-4 py-2`}>
                <Plus size={15} /> Add keywords
              </button>
            </>
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
              <div className="flex flex-wrap justify-center gap-2">
                <button onClick={() => setShowAdd(true)} className={`${BTN_PRIMARY} px-4 py-2`}>
                  <Plus size={15} /> Add your first keywords
                </button>
                <button onClick={() => setShowImport(true)} className={`${BTN_GHOST} px-4 py-2`}>
                  <FileSpreadsheet size={15} /> Import from Excel
                </button>
              </div>
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
                <th scope="col" className="px-5 py-3 font-medium text-left sticky left-0 bg-white">
                  Keyword
                </th>
                {months.map((m) => (
                  <th key={m} scope="col" className="px-3 py-3 font-medium text-center whitespace-nowrap">
                    {shortMonthLabel(m)}
                  </th>
                ))}
                {canDelete && <th scope="col" className="px-4 py-3 w-10"><span className="sr-only">Actions</span></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((row) => (
                <KeywordRow
                  key={row.id}
                  row={row}
                  months={months}
                  rowDirty={dirtyByRow[row.id]}
                  canEdit={canEdit}
                  canDelete={canDelete}
                  onCell={setCell}
                  onDelete={setConfirmDelete}
                />
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
          existingTerms={(rows || []).map((r) => r.term)}
          onClose={() => setShowAdd(false)}
          onAdded={load}
        />
      )}

      {showImport && (
        <BulkImportModal
          projectId={project.id}
          onClose={() => setShowImport(false)}
          onImported={load}
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

function AddKeywordsModal({ projectId, existingTerms, onClose, onAdded }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const toast = useToast();
  const inputRef = useRef(null);

  // Terms are lowercased server-side, so "Yoga" and "yoga" on two lines are the
  // same keyword. De-duplicate here rather than sending both and relying on the
  // second one to be rejected.
  const { terms, duplicateCount, alreadyCount } = useMemo(() => {
    const existing = new Set((existingTerms || []).map((t) => t.trim().toLowerCase()));
    const seen = new Set();
    const out = [];
    let dupes = 0;
    let already = 0;
    for (const line of text.split(/\r?\n/)) {
      const term = line.trim().toLowerCase();
      if (!term) continue;
      if (seen.has(term)) {
        dupes += 1;
        continue;
      }
      seen.add(term);
      if (existing.has(term)) {
        already += 1;
        continue;
      }
      out.push(term);
    }
    return { terms: out, duplicateCount: dupes, alreadyCount: already };
  }, [text, existingTerms]);

  const submit = async () => {
    if (!terms.length || busy) return;
    setBusy(true);
    setError(null);
    let added = 0;
    let skipped = 0;
    const failed = [];

    // Was one awaited request per term, strictly serial — pasting 80 keywords
    // meant 80 sequential round trips. Runs a few at a time now; the cap keeps a
    // large paste from opening a hundred parallel connections.
    const CONCURRENCY = 6;
    const queue = [...terms];
    const worker = async () => {
      while (queue.length) {
        const term = queue.shift();
        try {
          await api(`/projects/${projectId}/keywords`, { method: "POST", body: { term } });
          added += 1;
        } catch (err) {
          // 409 is the server telling us it's already tracked — not a failure
          // worth making the user re-check.
          if (err.status === 409) skipped += 1;
          else failed.push(term);
        }
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(CONCURRENCY, terms.length) }, worker)
    );

    setBusy(false);
    await onAdded();
    if (added) toast.success(`Added ${added} keyword${added === 1 ? "" : "s"}.`);
    if (skipped) toast.info(`${skipped} already tracked and skipped.`);
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
      {(duplicateCount > 0 || alreadyCount > 0) && (
        <p className="text-xs text-stone-500 mt-2">
          {duplicateCount > 0 && `${duplicateCount} repeated line${duplicateCount === 1 ? "" : "s"} will be sent once. `}
          {alreadyCount > 0 && `${alreadyCount} already tracked and will be skipped.`}
        </p>
      )}
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

/**
 * Excel import. This and ImportResult were written months ago and left sitting
 * in Dashboard.jsx, defined but never rendered — so the endpoints behind them
 * (and the styled template generator) were unreachable. Moved here and wired to
 * the toolbar button above.
 */
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

          <p className="mt-3 text-xs text-stone-400">
            This adds the keywords only. Enter each month&apos;s position on the grid afterwards.
          </p>

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
