import { useEffect, useMemo, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TabIndent } from "../lib/tabIndent";
import {
  AlertTriangle,
  Bold,
  ChevronLeft,
  Italic,
  List,
  ListOrdered,
  Lock,
  Heading2,
  LoaderCircle,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { api, BASE, getToken } from "../api";
import { ErrorNote, BTN_PRIMARY, BTN_GHOST, INPUT_CLS, isAuthor, isReportDeleter, isReportSender } from "../ui";
import { useToast } from "../toast.jsx";
import { createBlobNode } from "../lib/blobNode";
import {
  applyFormat,
  chipLabel,
  defaultFormatId,
} from "../lib/blobFormats";
import ReportDocument from "./ReportDocument";
import ReportDocumentEditor from "./ReportDocumentEditor";
import DownloadPdfButton from "../lib/DownloadPdfButton";
import SendReportButton from "../lib/SendReportButton";

const GROUP_ORDER = ["GA4", "GSC", "Moz", "Changes"];

export function blobInsertNodes(item) {
  return [
    {
      type: "blob",
      attrs: {
        name: item.name,
        kind: item.kind,
        format: defaultFormatId(item.type, item.kind),
        label: item.label,
      },
    },
    { type: "text", text: " " },
  ];
}
const STATUS_BADGE = {
  draft: "bg-emerald-100 text-emerald-700",
  in_review: "bg-amber-100 text-amber-700",
  sent: "bg-stone-200 text-stone-600",
};

const emptyDoc = () => ({ type: "doc", content: [{ type: "paragraph" }] });

function lastCompletedMonth() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function buildPaletteItems(blobs) {
  const items = [];
  for (const b of blobs) {
    items.push({
      key: `${b.name}:value`,
      name: b.name,
      kind: "value",
      type: b.type,
      label: chipLabel(b, "value"),
      group: b.group,
      search: `${b.label} ${b.group} ${b.name}`.toLowerCase(),
    });
    if (b.deltaValue !== null && b.deltaValue !== undefined) {
      items.push({
        key: `${b.name}:delta`,
        name: b.name,
        kind: "delta",
        type: b.type,
        label: chipLabel(b, "delta"),
        group: "Changes",
        search: `${b.label} change delta ${b.group} ${b.name}`.toLowerCase(),
      });
    }
  }
  return items;
}

export function groupedItems(items) {
  const by = {};
  for (const it of items) (by[it.group] ||= []).push(it);
  const order = [...GROUP_ORDER, ...Object.keys(by).filter((g) => !GROUP_ORDER.includes(g))];
  return order.filter((g) => by[g]?.length).map((g) => [g, by[g]]);
}

function findUnresolved(doc, blobsByName) {
  const out = [];
  const walk = (node) => {
    if (!node) return;
    if (node.type === "blob") {
      const blob = blobsByName.get(node.attrs?.name);
      const resolved = blob ? applyFormat(blob, node.attrs.kind, node.attrs.format) : null;
      if (resolved === null) out.push({ name: node.attrs?.name, kind: node.attrs?.kind, label: node.attrs?.label });
    }
    (node.content || []).forEach(walk);
  };
  walk(doc);
  return out;
}

export function ReportsPanel({ user, project }) {
  const toast = useToast();
  const [versions, setVersions] = useState(null);
  const [error, setError] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [period, setPeriod] = useState(lastCompletedMonth());
  const [generating, setGenerating] = useState(false);
  const [genMsg, setGenMsg] = useState(null);
  const canDelete = isReportDeleter(user);
  const canSend = isReportSender(user);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [sentAck, setSentAck] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const load = () => {
    setError(null);
    api(`/reports?projectId=${project.id}`)
      .then((d) => setVersions(d.versions))
      .catch((e) => setError(e.message));
  };
  useEffect(() => {
    load();
  }, [project.id]);

  const generate = async () => {
    if (!period || generating) return;
    setGenerating(true);
    setGenMsg(null);
    try {
      const res = await fetch(`${BASE}/api/reports/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ projectId: project.id, periodKey: period }),
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        const maturing = period === currentMonth();
        setGenMsg({
          tone: "ok",
          text: maturing
            ? `Report generated for ${period} (in progress — data still maturing).`
            : `Report generated for ${period}.`,
        });
        toast.success(`Report generated for ${period}.`, { title: "Report ready" });
        load();
      } else if (res.status === 409) {
        setGenMsg({ tone: "warn", text: `An unsent report for ${period} already exists — see the list below.` });
        toast.info(`An unsent report for ${period} already exists.`);
      } else if (res.status === 503) {
        setGenMsg({ tone: "warn", text: "Google timed out, please try again." });
        toast.error("Google timed out, please try again.", { title: "Couldn't generate" });
      } else if (res.status === 422) {
        setGenMsg({ tone: "warn", text: data.error || `Can't generate a report for ${period} yet.` });
        toast.error(data.error || `Can't generate a report for ${period} yet.`, { title: "Couldn't generate" });
      } else {
        setGenMsg({ tone: "warn", text: data.error || "Couldn't generate — try again." });
        toast.error(data.error || "Couldn't generate — try again.", { title: "Couldn't generate" });
      }
    } catch {
      setGenMsg({ tone: "warn", text: "Couldn't generate — try again." });
      toast.error("Couldn't generate — try again.", { title: "Couldn't generate" });
    } finally {
      setGenerating(false);
    }
  };

  const askDelete = (v) => {
    setSentAck(false);
    setPendingDelete(v);
  };
  const closeDelete = () => {
    setPendingDelete(null);
    setSentAck(false);
  };

  const confirmDelete = async () => {
    if (!pendingDelete || deleting) return;
    setDeleting(true);
    try {
      await api(`/reports/${pendingDelete.id}`, { method: "DELETE" });
      setGenMsg({ tone: "ok", text: `Report #${pendingDelete.id} (${pendingDelete.periodKey}) deleted.` });
      toast.success(`Report #${pendingDelete.id} (${pendingDelete.periodKey}) deleted.`, { title: "Report deleted" });
      closeDelete();
      load();
    } catch (e) {
      setGenMsg({ tone: "warn", text: e.message || "Couldn't delete the report." });
      toast.error(e.message || "Couldn't delete the report.", { title: "Delete failed" });
      closeDelete();
    } finally {
      setDeleting(false);
    }
  };

  if (!isAuthor(user)) {
    return <p className="text-sm text-stone-500">Only report authors can open the report editor.</p>;
  }

  if (openId != null) {
    return (
      <ReportEditor
        versionId={openId}
        canSend={canSend}
        onBack={() => {
          setOpenId(null);
          load();
        }}
      />
    );
  }

  return (
    <div className="w-full max-w-3xl">
      <h2 className="text-lg font-bold text-stone-900 font-display">Reports</h2>
      <p className="text-sm text-stone-500 mt-0.5">Open a draft to write its content. Locked versions open read-only.</p>

      <div className="mt-4 flex flex-wrap items-end gap-2 bg-white border border-stone-200 rounded-xl p-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Report month</label>
          <input
            type="month"
            value={period}
            max={currentMonth()}
            onChange={(e) => setPeriod(e.target.value)}
            aria-label="Report month"
            className={`${INPUT_CLS} w-auto`}
          />
        </div>
        <button onClick={generate} disabled={generating || !period} className={`${BTN_PRIMARY} px-4 py-2`}>
          {generating ? (
            <>
              <LoaderCircle size={15} className="animate-spin" /> Generating…
            </>
          ) : (
            <>
              <Plus size={15} /> Generate report
            </>
          )}
        </button>
      </div>

      {genMsg && (
        <p
          className={`text-sm rounded-lg px-3 py-2 mt-3 border ${
            genMsg.tone === "ok"
              ? "bg-emerald-50 border-emerald-100 text-emerald-800"
              : "bg-amber-50 border-amber-100 text-amber-800"
          }`}
        >
          {genMsg.text}
        </p>
      )}

      <ErrorNote>{error}</ErrorNote>

      {versions == null ? (
        <div className="py-10 flex justify-center">
          <LoaderCircle size={20} className="text-orange-600 animate-spin" />
        </div>
      ) : versions.length === 0 ? (
        <p className="mt-6 text-sm text-stone-500 bg-white border border-stone-200 rounded-xl p-6">
          No report versions yet. Pick a month above and generate one — it'll appear here to edit.
        </p>
      ) : (
        <div className="mt-4 bg-white border border-stone-200 rounded-xl divide-y divide-stone-100">
          {versions.map((v) => (
            <div key={v.id} className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-stone-900">
                  {v.periodKey}
                  {v.parentVersionId ? <span className="text-stone-400"> · forked from #{v.parentVersionId}</span> : null}
                </p>
                <p className="text-xs text-stone-400">#{v.id} · {v.createdAt}</p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[v.status] || "bg-stone-200 text-stone-600"}`}>
                  {v.status}
                </span>
                <DownloadPdfButton
                  versionId={v.id}
                  projectName={project.name}
                  periodKey={v.periodKey}
                  onError={(m) => setGenMsg({ tone: "warn", text: m })}
                />
                {canSend && (
                  <SendReportButton
                    versionId={v.id}
                    periodKey={v.periodKey}
                    projectId={project.id}
                  />
                )}
                <button onClick={() => setOpenId(v.id)} className={`${BTN_GHOST} px-3 py-1.5`}>
                  {v.status === "draft" ? "Edit" : "Open"}
                </button>
                {canDelete && (
                  <button
                    onClick={() => askDelete(v)}
                    className="inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    aria-label={`Delete report ${v.periodKey}`}
                    title="Delete report"
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {pendingDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
        >
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-5">
            <div className="flex items-start gap-3">
              <span className="shrink-0 rounded-full bg-red-100 text-red-600 p-2">
                <AlertTriangle size={18} />
              </span>
              <div className="min-w-0">
                <h3 className="text-base font-bold text-stone-900 font-display">
                  Delete this report?
                </h3>
                {pendingDelete.status === "sent" ? (
                  <p className="text-sm text-stone-600 mt-1">
                    Report <span className="font-data">#{pendingDelete.id}</span> ({pendingDelete.periodKey}) was{" "}
                    <strong>sent to the client</strong>. Deleting it permanently removes it and{" "}
                    <strong>may break the client's link</strong>. This cannot be undone.
                  </p>
                ) : (
                  <p className="text-sm text-stone-600 mt-1">
                    Delete report <span className="font-data">#{pendingDelete.id}</span> ({pendingDelete.periodKey})?
                    This can't be undone.
                  </p>
                )}
              </div>
            </div>

            {pendingDelete.status === "sent" && (
              <label className="flex items-start gap-2 mt-3 text-sm text-stone-700 cursor-pointer">
                <input
                  type="checkbox"
                  checked={sentAck}
                  onChange={(e) => setSentAck(e.target.checked)}
                  className="mt-0.5"
                />
                I understand this was sent and may break the client's link.
              </label>
            )}

            <div className="flex justify-end gap-2 mt-5">
              <button onClick={closeDelete} disabled={deleting} className={`${BTN_GHOST} px-3 py-1.5`}>
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleting || (pendingDelete.status === "sent" && !sentAck)}
                className="inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {deleting ? (
                  <>
                    <LoaderCircle size={15} className="animate-spin" /> Deleting…
                  </>
                ) : pendingDelete.status === "sent" ? (
                  <>
                    <Trash2 size={15} /> Permanently delete
                  </>
                ) : (
                  <>
                    <Trash2 size={15} /> Delete
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReportEditor({ versionId, onBack, canSend = false }) {
  const [version, setVersion] = useState(null);
  const [blobs, setBlobs] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([api(`/reports/${versionId}`), api(`/reports/${versionId}/blobs`)])
      .then(([v, b]) => {
        if (cancelled) return;
        setVersion(v.version);
        setBlobs(b.blobs);
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [versionId]);

  return (
    <div className="w-full">
      <button onClick={onBack} className="flex items-center gap-1 text-xs text-stone-400 hover:text-stone-700 mb-3">
        <ChevronLeft size={14} /> Back to reports
      </button>

      {loading ? (
        <div className="py-16 flex justify-center">
          <LoaderCircle size={22} className="text-orange-600 animate-spin" />
        </div>
      ) : error || !version || !blobs ? (
        <ErrorNote>{error || "Could not load this report version."}</ErrorNote>
      ) : version.content?.type === "report_document" ? (
        <ReportDocumentEditor key={versionId} version={version} blobs={blobs} canSend={canSend} />
      ) : (
        <ReportEditorInner key={versionId} version={version} blobs={blobs} canSend={canSend} />
      )}
    </div>
  );
}

function ReportEditorInner({ version, blobs, canSend = false }) {
  const isDraft = version.status === "draft";
  const blobsByName = useMemo(() => new Map(blobs.map((b) => [b.name, b])), [blobs]);
  const paletteItems = useMemo(() => buildPaletteItems(blobs), [blobs]);

  const [doc, setDoc] = useState(() => {
    const c = version.content;
    return c && c.type === "doc" ? c : emptyDoc();
  });
  const [sugg, setSugg] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [saveError, setSaveError] = useState(null);

  // The whole document is local state behind a manual Save draft button, so
  // without this a tab close or a stray "Back to reports" discarded everything
  // written since the last save.
  const [dirty, setDirty] = useState(false);
  const docTimer = useRef(null);
  useEffect(() => () => clearTimeout(docTimer.current), []);

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (e) => {
      e.preventDefault();
      e.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const suggestion = useMemo(() => makeSuggestion({ paletteItems, setSugg }), [paletteItems]);
  const BlobNode = useMemo(() => createBlobNode(blobsByName), [blobsByName]);

  const editor = useEditor(
    {
      editable: isDraft,
      immediatelyRender: false,
      extensions: [StarterKit, TabIndent, BlobNode.configure({ suggestion })],
      content: doc,
      editorProps: {
        attributes: {
          class: "report-prose focus:outline-none min-h-[300px] px-4 py-3",
        },
      },
      // Debounced. `doc` drives findUnresolved over the whole document and the
      // live PreviewPane, so extracting and re-rendering on every keystroke made
      // typing visibly lag on a long report. The editor itself stays
      // uncontrolled, so input is never held up — only the derived views settle
      // a moment later. `dirty` is set immediately: the unload guard must not
      // depend on a timer.
      onUpdate: ({ editor }) => {
        setDirty(true);
        clearTimeout(docTimer.current);
        docTimer.current = setTimeout(() => setDoc(editor.getJSON()), 300);
      },
    },
    []
  );

  const unresolved = useMemo(() => findUnresolved(doc, blobsByName), [doc, blobsByName]);

  const insert = (item) => {
    if (!editor || !isDraft) return;
    editor.chain().focus().insertContent(blobInsertNodes(item)).run();
  };

  const save = async () => {
    if (!editor) return;
    setSaving(true);
    setSaveError(null);
    try {
      const content = editor.getJSON();
      await api(`/reports/${version.id}/content`, { method: "PATCH", body: { content } });
      setSavedAt(new Date());
      setDirty(false);
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="text-lg font-bold text-stone-900 font-display">
            Report content · {version.periodKey}
          </h2>
          <p className="text-xs text-stone-400">#{version.id}</p>
        </div>
        <div className="flex items-center gap-2">
          {savedAt && !saveError && (
            <span className="text-xs text-emerald-600">Saved {savedAt.toLocaleTimeString()}</span>
          )}
          <DownloadPdfButton versionId={version.id} periodKey={version.periodKey} label onError={setSaveError} />
          {isDraft ? (
            <button onClick={save} disabled={saving} className={`${BTN_PRIMARY} px-3 py-1.5`}>
              {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />} Save draft
            </button>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-xs font-medium text-stone-500 bg-stone-100 border border-stone-200 px-2.5 py-1 rounded-lg">
              <Lock size={13} /> {version.status} — locked
            </span>
          )}
        </div>
      </div>

      {!isDraft && (
        <p className="mb-3 text-sm text-stone-600 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 flex items-center gap-2">
          <Lock size={14} /> This report is <b>{version.status}</b> and can't be edited. You're viewing it read-only.
        </p>
      )}
      <ErrorNote>{saveError}</ErrorNote>

      <FinalizeGate unresolved={unresolved} isDraft={isDraft} />

      <div className="mt-3 grid grid-cols-1 lg:grid-cols-[15rem_minmax(0,1fr)_minmax(0,1fr)] gap-4">
        {isDraft && <BlobPalette items={paletteItems} onInsert={insert} />}

        <div className="min-w-0">
          {isDraft && <Toolbar editor={editor} />}
          <div className="bg-white border border-stone-200 rounded-xl overflow-hidden">
            <EditorContent editor={editor} />
          </div>
          <p className="mt-1.5 text-xs text-stone-400">
            Type <kbd className="px-1 rounded bg-stone-100 border border-stone-200">/</kbd> to insert data, or click a field. Click a chip to change its format.
          </p>
        </div>

        <PreviewPane doc={doc} blobsByName={blobsByName} />
      </div>

      <SuggestionMenu sugg={sugg} />
    </div>
  );
}

export function Toolbar({ editor }) {
  if (!editor) return null;
  const Btn = ({ on, onClick, children, label }) => (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={`p-1.5 rounded-md transition-colors ${on ? "bg-orange-50 text-orange-700" : "text-stone-500 hover:bg-stone-100 hover:text-stone-900"}`}
    >
      {children}
    </button>
  );
  return (
    <div className="flex items-center gap-1 mb-2">
      <Btn label="Bold" on={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}>
        <Bold size={15} />
      </Btn>
      <Btn label="Italic" on={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}>
        <Italic size={15} />
      </Btn>
      <Btn label="Heading" on={editor.isActive("heading", { level: 2 })} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
        <Heading2 size={15} />
      </Btn>
      <Btn label="Bullet list" on={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>
        <List size={15} />
      </Btn>
      <Btn label="Numbered list" on={editor.isActive("orderedList")} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
        <ListOrdered size={15} />
      </Btn>
    </div>
  );
}

export function BlobPalette({ items, onInsert }) {
  const [q, setQ] = useState("");
  const filtered = q ? items.filter((i) => i.search.includes(q.toLowerCase())) : items;
  const groups = groupedItems(filtered);
  return (
    <div className="lg:sticky lg:top-4 self-start">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Insert data</p>
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fields…" className={INPUT_CLS} />
      <div className="mt-2 max-h-[60vh] overflow-y-auto pr-1">
        {groups.length === 0 && <p className="text-xs text-stone-400 py-3">No matching fields.</p>}
        {groups.map(([group, gi]) => (
          <div key={group} className="mb-2">
            <p className="px-1 text-[11px] font-semibold text-stone-400">{group}</p>
            {gi.map((it) => (
              <button
                key={it.key}
                onClick={() => onInsert(it)}
                className="w-full flex items-center gap-1.5 text-left px-2 py-1.5 rounded-lg text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700 transition-colors"
              >
                <Plus size={13} className="shrink-0 text-stone-400" />
                <span className="truncate">{it.label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function FinalizeGate({ unresolved, isDraft }) {
  const blocked = unresolved.length > 0;
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 ${
        blocked ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"
      }`}
    >
      <p className={`text-sm flex items-center gap-1.5 ${blocked ? "text-red-700" : "text-emerald-700"}`}>
        {blocked ? (
          <>
            <AlertTriangle size={14} />
            {unresolved.length} data blob{unresolved.length > 1 ? "s" : ""} can't be resolved — fix before finalizing.
          </>
        ) : (
          <>All inserted data resolves.</>
        )}
      </p>
      {/* The Finalize button that used to sit here was hard-coded `disabled`
          with the tooltip "Submit / review arrives in a later slice" — shipped UI
          promising an action nobody could take. The validation message above is
          the useful half and stays; put the button back when the review flow
          actually exists. */}
    </div>
  );
}

function PreviewPane({ doc, blobsByName }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Live preview</p>
      <div className="report-prose bg-white border border-stone-200 rounded-xl px-4 py-3 min-h-[300px] text-stone-800">
        {renderNodes(doc?.content, blobsByName, "p")}
      </div>
    </div>
  );
}

function renderNodes(nodes, map, keyPrefix) {
  if (!nodes) return null;
  return nodes.map((n, i) => renderNode(n, map, `${keyPrefix}-${i}`));
}

function renderNode(node, map, key) {
  switch (node.type) {
    case "paragraph":
      return <p key={key}>{renderNodes(node.content, map, key)}</p>;
    case "heading": {
      const L = node.attrs?.level || 2;
      const Tag = `h${L}`;
      return <Tag key={key}>{renderNodes(node.content, map, key)}</Tag>;
    }
    case "bulletList":
      return <ul key={key}>{renderNodes(node.content, map, key)}</ul>;
    case "orderedList":
      return <ol key={key}>{renderNodes(node.content, map, key)}</ol>;
    case "listItem":
      return <li key={key}>{renderNodes(node.content, map, key)}</li>;
    case "blockquote":
      return <blockquote key={key}>{renderNodes(node.content, map, key)}</blockquote>;
    case "codeBlock":
      return (
        <pre key={key}>
          <code>{renderNodes(node.content, map, key)}</code>
        </pre>
      );
    case "horizontalRule":
      return <hr key={key} />;
    case "hardBreak":
      return <br key={key} />;
    case "text":
      return renderText(node, key);
    case "blob":
      return renderBlob(node, map, key);
    default:
      return node.content ? <span key={key}>{renderNodes(node.content, map, key)}</span> : null;
  }
}

function renderText(node, key) {
  let el = node.text;
  for (const m of node.marks || []) {
    if (m.type === "bold") el = <strong>{el}</strong>;
    else if (m.type === "italic") el = <em>{el}</em>;
    else if (m.type === "strike") el = <s>{el}</s>;
    else if (m.type === "code") el = <code className="px-1 rounded bg-stone-100 font-data text-sm">{el}</code>;
  }
  return <span key={key}>{el}</span>;
}

function renderBlob(node, map, key) {
  const { name, kind, format, label } = node.attrs || {};
  const blob = map.get(name);
  const resolved = blob ? applyFormat(blob, kind, format) : null;
  if (resolved === null) {
    return (
      <span key={key} className="inline-flex items-center gap-1 rounded bg-red-50 text-red-700 border border-red-200 px-1 text-sm">
        <AlertTriangle size={11} /> {label || name || "unknown"}
      </span>
    );
  }
  return (
    <span key={key} className="font-data font-semibold text-stone-900">
      {resolved}
    </span>
  );
}

export function makeSuggestion({ paletteItems, setSugg }) {
  return {
    char: "/",
    allowSpaces: false,
    startOfLine: false,
    items: ({ query }) => {
      const q = (query || "").toLowerCase();
      return paletteItems.filter((i) => i.search.includes(q)).slice(0, 10);
    },
    command: ({ editor, range, props }) => {
      editor.chain().focus().insertContentAt(range, blobInsertNodes(props)).run();
    },
    render: () => {
      const local = { items: [], command: null, index: 0, rect: null };
      const flush = () => setSugg({ ...local });
      return {
        onStart: (props) => {
          local.items = props.items;
          local.command = props.command;
          local.index = 0;
          local.rect = props.clientRect;
          flush();
        },
        onUpdate: (props) => {
          local.items = props.items;
          local.command = props.command;
          local.rect = props.clientRect;
          if (local.index >= props.items.length) local.index = 0;
          flush();
        },
        onKeyDown: (props) => {
          const { key } = props.event;
          const n = local.items.length;
          if (!n) return false;
          if (key === "ArrowDown") {
            local.index = (local.index + 1) % n;
            flush();
            return true;
          }
          if (key === "ArrowUp") {
            local.index = (local.index - 1 + n) % n;
            flush();
            return true;
          }
          if (key === "Enter") {
            const it = local.items[local.index];
            if (it && local.command) local.command(it);
            return true;
          }
          if (key === "Escape") {
            setSugg(null);
            return true;
          }
          return false;
        },
        onExit: () => setSugg(null),
      };
    },
  };
}

export function SuggestionMenu({ sugg }) {
  if (!sugg || !sugg.items?.length) return null;
  const rect = typeof sugg.rect === "function" ? sugg.rect() : null;
  if (!rect) return null;
  const style = { position: "fixed", left: rect.left, top: rect.bottom + 4, zIndex: 50 };
  return (
    <div style={style} className="w-72 max-h-64 overflow-auto rounded-lg border border-stone-200 bg-white shadow-xl py-1">
      {sugg.items.map((it, i) => (
        <button
          key={it.key}
          onMouseDown={(e) => {
            e.preventDefault();
            sugg.command?.(it);
          }}
          className={`w-full flex items-center justify-between gap-2 px-3 py-1.5 text-sm ${
            i === sugg.index ? "bg-orange-50 text-orange-700" : "text-stone-700 hover:bg-stone-100"
          }`}
        >
          <span className="truncate">{it.label}</span>
          <span className="text-xs text-stone-400">{it.group}</span>
        </button>
      ))}
    </div>
  );
}
