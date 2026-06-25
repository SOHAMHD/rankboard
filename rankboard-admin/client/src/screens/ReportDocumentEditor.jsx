/* ════════════════════════════════════════════════════════════════════
   REPORT DOCUMENT EDITOR — make the generated block document EDITABLE.

   PRODUCT BOUNDARY (enforced here): apart from the DATA VALUES, everything is
   editable. Editable = document STRUCTURE (reorder / delete / add free-text /
   re-add a removed template section) and all NARRATIVE TEXT (with blob-chips).
   IMMUTABLE = the data values — data_table cells, metric_grid metrics, chart
   series, backlinks list, header. Those blocks are MOVE / DELETE / RE-ADD only;
   their inner values are rendered exactly as read-only and never edited.

   REUSE (no rebuilding):
     • Narrative blocks host the EXISTING TipTap chip editor — createBlobNode
       (lib/blobNode.jsx) + the "/" suggestion, palette, Toolbar and format picker
       exported from ReportEditor.jsx. A chip stores {name,kind,format,label} and
       resolves to a FROZEN value (immutable; format is display-only). The palette
       values come from GET /api/reports/{id}/blobs.
     • DATA blocks reuse the read-only renderers from ReportDocument.jsx verbatim.
     • SAVE goes through the EXISTING PATCH /api/reports/{id}/content (draft-only,
       author-gated). data_json is never touched — all edits live in content_json.

   A narrative block gains a `doc` (TipTap/ProseMirror JSON) once it enters the
   editor; the read-only renderer (ReportDocument.jsx) prefers `doc` and falls
   back to the original paragraphs/bullets, so a saved-then-reopened document
   round-trips through the SAME schema.

   A locked/sent version is shown READ-ONLY (no crash, clear banner). Re-adding a
   removed template section rebuilds it from the frozen data_json via the
   read-only GET /api/reports/{id}/template-blocks endpoint.
   ════════════════════════════════════════════════════════════════════ */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import {
  ChevronUp,
  ChevronDown,
  Trash2,
  Plus,
  Save,
  LoaderCircle,
  Lock,
  Type,
  LayoutGrid,
} from "lucide-react";
import { api } from "../api";
import { ErrorNote, BTN_PRIMARY, BTN_GHOST } from "../ui";
import { createBlobNode } from "../lib/blobNode";
import {
  makeSuggestion,
  SuggestionMenu,
  BlobPalette,
  buildPaletteItems,
  blobInsertNodes,
  Toolbar,
} from "./ReportEditor";
import ReportDocument, {
  HeaderBlock,
  MetricGridBlock,
  DataTableBlock,
  ChartBlock,
  BacklinksBlock,
} from "./ReportDocument";

// New blocks need a stable, unique id. Browser context — Date.now()/Math.random
// are fine here (unlike workflow scripts). Prefix marks an author-added block.
function newId(prefix) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

function newFreeTextBlock() {
  return {
    id: newId("freetext"),
    type: "narrative",
    role: "free_text",
    title: "",
    paragraphs: [],
    bullets: [],
    editable: true,
    doc: { type: "doc", content: [{ type: "paragraph" }] },
  };
}

// A narrative block's editable representation: prefer an already-edited `doc`,
// else build one from the templated paragraphs/bullets so the chip editor has
// something to edit. Kept in sync with ReportDocument's read-only fallback.
function docFromNarrative(block) {
  if (block.doc && block.doc.type === "doc") return block.doc;
  const content = [];
  for (const p of block.paragraphs || []) {
    content.push({ type: "paragraph", content: p ? [{ type: "text", text: p }] : [] });
  }
  const bullets = block.bullets || [];
  if (bullets.length) {
    content.push({
      type: "bulletList",
      content: bullets.map((b) => ({
        type: "listItem",
        content: [{ type: "paragraph", content: b ? [{ type: "text", text: b }] : [] }],
      })),
    });
  }
  if (!content.length) content.push({ type: "paragraph" });
  return { type: "doc", content };
}

const DATA_BLOCK_TYPES = new Set([
  "report_header",
  "metric_grid",
  "data_table",
  "chart",
  "backlinks_list",
]);

function ReadOnlyDataBlock({ block }) {
  switch (block.type) {
    case "report_header":
      return <HeaderBlock block={block} />;
    case "metric_grid":
      return <MetricGridBlock block={block} />;
    case "data_table":
      return <DataTableBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "backlinks_list":
      return <BacklinksBlock block={block} />;
    default:
      return null;
  }
}

// ════════════════════════════════════════════════════════════════════
// ENTRY — draft → editable; locked/sent → read-only.
// ════════════════════════════════════════════════════════════════════
export default function ReportDocumentEditor({ version, blobs }) {
  if (version.status !== "draft") {
    return (
      <div className="w-full">
        <p className="mb-3 text-sm text-stone-600 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 flex items-center gap-2">
          <Lock size={14} /> This report is <b>{version.status}</b> and can't be edited. You're viewing it read-only.
        </p>
        <ReportDocument version={version} blobs={blobs} />
      </div>
    );
  }
  return <EditableDoc version={version} blobs={blobs} />;
}

// ── one narrative block, edited with the EXISTING TipTap chip editor ───────────
function NarrativeEditor({ block, BlobNode, suggestion, onDocChange, onFocusEditor }) {
  const initialDoc = useMemo(() => docFromNarrative(block), [block.id]);

  const editor = useEditor(
    {
      editable: true,
      immediatelyRender: false,
      extensions: [StarterKit, BlobNode.configure({ suggestion })],
      content: initialDoc,
      editorProps: {
        attributes: { class: "report-prose focus:outline-none min-h-[64px] px-3 py-2" },
      },
      onUpdate: ({ editor }) => onDocChange(block.id, editor.getJSON()),
      onFocus: ({ editor }) => onFocusEditor(editor),
    },
    []
  );

  // Seed the block's doc once so even an UNEDITED narrative persists as a doc on
  // save (consistent shape; the read-only renderer prefers doc).
  useEffect(() => {
    onDocChange(block.id, initialDoc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      {block.title ? (
        <h3 className="text-base font-bold text-stone-900 font-display mb-2">{block.title}</h3>
      ) : (
        <p className="text-[11px] font-semibold uppercase tracking-wider text-stone-400 mb-1.5">Free text</p>
      )}
      <Toolbar editor={editor} />
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

// ── structure controls that wrap EVERY block ──────────────────────────────────
function BlockFrame({ index, total, isData, onUp, onDown, onDelete, onAddTextBelow, children }) {
  return (
    <div className="group relative rounded-xl border border-stone-200 bg-stone-50/40 p-2">
      <div className="flex items-center justify-between mb-1.5 px-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-300">
          {isData ? "Data · move / delete only" : "Editable text"}
        </span>
        <div className="flex items-center gap-0.5">
          <IconBtn label="Move up" disabled={index === 0} onClick={onUp}>
            <ChevronUp size={15} />
          </IconBtn>
          <IconBtn label="Move down" disabled={index === total - 1} onClick={onDown}>
            <ChevronDown size={15} />
          </IconBtn>
          <IconBtn label="Delete block" onClick={onDelete} danger>
            <Trash2 size={14} />
          </IconBtn>
        </div>
      </div>
      <div className="px-1">{children}</div>
      <div className="mt-1.5 flex justify-center">
        <button
          type="button"
          onClick={onAddTextBelow}
          className="opacity-0 group-hover:opacity-100 transition-opacity inline-flex items-center gap-1 text-[11px] text-stone-400 hover:text-orange-700"
        >
          <Plus size={12} /> Add text below
        </button>
      </div>
    </div>
  );
}

function IconBtn({ label, onClick, disabled, danger, children }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`p-1 rounded-md transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
        danger ? "text-stone-400 hover:text-red-600 hover:bg-red-50" : "text-stone-400 hover:text-stone-700 hover:bg-stone-100"
      }`}
    >
      {children}
    </button>
  );
}

// ── the editable document ─────────────────────────────────────────────────────
function EditableDoc({ version, blobs }) {
  const blobsByName = useMemo(() => new Map((blobs || []).map((b) => [b.name, b])), [blobs]);
  const paletteItems = useMemo(() => buildPaletteItems(blobs || []), [blobs]);
  const BlobNode = useMemo(() => createBlobNode(blobsByName), [blobsByName]);

  const [sugg, setSugg] = useState(null);
  const suggestion = useMemo(() => makeSuggestion({ paletteItems, setSugg }), [paletteItems]);
  const activeEditorRef = useRef(null);

  const [blocks, setBlocks] = useState(() =>
    JSON.parse(JSON.stringify(version.content?.blocks || []))
  );
  const [templateBlocks, setTemplateBlocks] = useState([]);
  const [addOpen, setAddOpen] = useState(false);

  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [saveError, setSaveError] = useState(null);

  // The canonical template (rebuilt server-side from the frozen data_json), so a
  // section deleted in a PRIOR session can still be re-added. Read-only fetch.
  useEffect(() => {
    let cancelled = false;
    api(`/reports/${version.id}/template-blocks`)
      .then((d) => !cancelled && setTemplateBlocks(d.blocks || []))
      .catch(() => !cancelled && setTemplateBlocks([]));
    return () => {
      cancelled = true;
    };
  }, [version.id]);

  // Stable callbacks (the TipTap onUpdate closure captures these once).
  const onDocChange = useCallback((id, doc) => {
    setBlocks((bs) => bs.map((b) => (b.id === id ? { ...b, doc } : b)));
  }, []);
  const onFocusEditor = useCallback((editor) => {
    activeEditorRef.current = editor;
  }, []);

  const move = (index, dir) => {
    setBlocks((bs) => {
      const j = index + dir;
      if (j < 0 || j >= bs.length) return bs;
      const next = bs.slice();
      [next[index], next[j]] = [next[j], next[index]];
      return next;
    });
  };
  const remove = (index) => setBlocks((bs) => bs.filter((_, i) => i !== index));
  const addTextAt = (index) =>
    setBlocks((bs) => {
      const next = bs.slice();
      next.splice(index + 1, 0, newFreeTextBlock());
      return next;
    });
  const addTextEnd = () => setBlocks((bs) => [...bs, newFreeTextBlock()]);
  const reAddSection = (tb) => {
    setBlocks((bs) => [...bs, JSON.parse(JSON.stringify(tb))]);
    setAddOpen(false);
  };

  // Insert a blob chip into the editor the author last focused.
  const insertBlob = (item) => {
    const editor = activeEditorRef.current;
    if (!editor) return;
    editor.chain().focus().insertContent(blobInsertNodes(item)).run();
  };

  const presentIds = useMemo(() => new Set(blocks.map((b) => b.id)), [blocks]);
  const missingSections = templateBlocks.filter((tb) => !presentIds.has(tb.id));

  const save = async () => {
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const content = { ...version.content, blocks };
      await api(`/reports/${version.id}/content`, { method: "PATCH", body: { content } });
      setSavedAt(new Date());
    } catch (e) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full">
      {/* ── header / save ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div>
          <h2 className="text-lg font-bold text-stone-900 font-display">
            Edit report · {version.periodKey}
          </h2>
          <p className="text-xs text-stone-400">#{version.id} · draft</p>
        </div>
        <div className="flex items-center gap-2">
          {savedAt && !saveError && (
            <span className="text-xs text-emerald-600">Saved {savedAt.toLocaleTimeString()}</span>
          )}
          <button onClick={save} disabled={saving} className={`${BTN_PRIMARY} px-3 py-1.5`}>
            {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />} Save draft
          </button>
        </div>
      </div>

      <ErrorNote>{saveError}</ErrorNote>

      <p className="mb-3 text-sm text-stone-500">
        Reorder, delete, and add blocks; edit any text block (type <kbd className="px-1 rounded bg-stone-100 border border-stone-200">/</kbd> to insert data). Data values are fixed and can't be edited.
      </p>

      {/* ── 2-pane: document · insert-data palette ── */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_15rem] gap-4">
        <div className="min-w-0 space-y-3">
          {blocks.map((block, i) => {
            const isData = DATA_BLOCK_TYPES.has(block.type);
            return (
              <BlockFrame
                key={block.id}
                index={i}
                total={blocks.length}
                isData={isData}
                onUp={() => move(i, -1)}
                onDown={() => move(i, 1)}
                onDelete={() => remove(i)}
                onAddTextBelow={() => addTextAt(i)}
              >
                {block.type === "narrative" ? (
                  <NarrativeEditor
                    block={block}
                    BlobNode={BlobNode}
                    suggestion={suggestion}
                    onDocChange={onDocChange}
                    onFocusEditor={onFocusEditor}
                  />
                ) : (
                  <ReadOnlyDataBlock block={block} />
                )}
              </BlockFrame>
            );
          })}

          {/* ── add controls ── */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button onClick={addTextEnd} className={`${BTN_GHOST} px-3 py-1.5`}>
              <Type size={14} /> Add text block
            </button>
            <div className="relative">
              <button
                onClick={() => setAddOpen((o) => !o)}
                disabled={missingSections.length === 0}
                title={missingSections.length === 0 ? "All template sections are in the document." : "Re-add a removed template section"}
                className={`${BTN_GHOST} px-3 py-1.5`}
              >
                <LayoutGrid size={14} /> Add section
                <ChevronDown size={13} className="text-stone-400" />
              </button>
              {addOpen && missingSections.length > 0 && (
                <div className="absolute left-0 top-full z-30 mt-1 w-64 max-h-72 overflow-auto rounded-lg border border-stone-200 bg-white shadow-xl py-1">
                  <p className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                    Removed sections (rebuilt from data)
                  </p>
                  {missingSections.map((tb) => (
                    <button
                      key={tb.id}
                      onClick={() => reAddSection(tb)}
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700"
                    >
                      <Plus size={13} className="shrink-0 text-stone-400" />
                      <span className="truncate">{tb.title || tb.type}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── insert-data palette (reused chip-editor palette) ── */}
        <div className="lg:sticky lg:top-4 self-start">
          <BlobPalette items={paletteItems} onInsert={insertBlob} />
          <p className="mt-2 text-[11px] text-stone-400">
            Click a field to insert it into the text block you last edited, or type
            <kbd className="mx-1 px-1 rounded bg-stone-100 border border-stone-200">/</kbd> in a text block.
          </p>
        </div>
      </div>

      {/* shared "/" suggestion menu (one instance for all narrative editors) */}
      <SuggestionMenu sugg={sugg} />
    </div>
  );
}
