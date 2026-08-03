import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TabIndent } from "../lib/tabIndent";
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
import DownloadPdfButton from "../lib/DownloadPdfButton";
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

const EDITABLE_TABLE_ID = "keywords";

const DATA_BLOCK_TYPES = new Set([
  "report_header",
  "metric_grid",
  "data_table",
  "chart",
  "backlinks_list",
]);

function ReadOnlyDataBlock({ block, hideTitle }) {
  switch (block.type) {
    case "report_header":
      return <HeaderBlock block={block} />;
    case "metric_grid":
      return <MetricGridBlock block={block} hideTitle={hideTitle} />;
    case "data_table":
      return <DataTableBlock block={block} hideTitle={hideTitle} />;
    case "chart":
      return <ChartBlock block={block} hideTitle={hideTitle} />;
    case "backlinks_list":
      return <BacklinksBlock block={block} hideTitle={hideTitle} />;
    default:
      return null;
  }
}

export default function ReportDocumentEditor({ version, blobs, canSend = false }) {
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
  return <EditableDoc version={version} blobs={blobs} canSend={canSend} />;
}

function NarrativeEditor({ block, BlobNode, suggestion, onDocChange, onFocusEditor }) {
  const initialDoc = useMemo(() => docFromNarrative(block), [block.id]);

  const editor = useEditor(
    {
      editable: true,
      immediatelyRender: false,
      extensions: [StarterKit, TabIndent, BlobNode.configure({ suggestion })],
      content: initialDoc,
      editorProps: {
        attributes: { class: "report-prose focus:outline-none min-h-[64px] px-3 py-2" },
      },
      onUpdate: ({ editor }) => onDocChange(block.id, editor.getJSON()),
      onFocus: ({ editor }) => onFocusEditor(editor),
    },
    []
  );

  useEffect(() => {
    onDocChange(block.id, initialDoc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <Toolbar editor={editor} />
      <div className="bg-white border border-stone-200 rounded-lg overflow-hidden">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

function TargetsGridEditor({ block, onSetValue }) {
  const columns = block.columns || [];
  const fields = block.fields || [];
  const values = block.values || {};
  return (
    <div>
      {columns.map((col) => (
        <div key={col.key} className="mb-4">
          <h4 className="text-sm font-semibold text-blue-700 mb-2">{col.label}</h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {fields.map((f) => (
              <label key={f.key} className="block">
                <span className="text-xs text-stone-500">{f.label}</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={(values[col.key] || {})[f.key] ?? ""}
                  onChange={(e) => onSetValue(block.id, col.key, f.key, e.target.value)}
                  placeholder="\u2014"
                  className="mt-0.5 w-full rounded-md border border-stone-200 px-2 py-1 text-sm font-data focus:border-blue-400 focus:outline-none"
                />
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function trimLogo(dataUrl) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      try {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        const ctx = c.getContext("2d");
        ctx.drawImage(img, 0, 0);
        const { data } = ctx.getImageData(0, 0, c.width, c.height);
        let top = c.height, left = c.width, right = 0, bottom = 0, found = false;
        for (let y = 0; y < c.height; y++) {
          for (let x = 0; x < c.width; x++) {
            const i = (y * c.width + x) * 4;
            const a = data[i + 3], r = data[i], g = data[i + 1], b = data[i + 2];
            const content = a > 12 && !(r > 245 && g > 245 && b > 245);
            if (content) {
              found = true;
              if (x < left) left = x;
              if (x > right) right = x;
              if (y < top) top = y;
              if (y > bottom) bottom = y;
            }
          }
        }
        if (!found) return resolve(dataUrl);
        const pad = 2;
        left = Math.max(0, left - pad); top = Math.max(0, top - pad);
        right = Math.min(c.width - 1, right + pad); bottom = Math.min(c.height - 1, bottom + pad);
        const w = right - left + 1, h = bottom - top + 1;
        const o = document.createElement("canvas");
        o.width = w; o.height = h;
        o.getContext("2d").drawImage(c, left, top, w, h, 0, 0, w, h);
        resolve(o.toDataURL("image/png"));
      } catch (e) {
        resolve(dataUrl);
      }
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}

function HeaderEditor({ block, onSetLogo }) {
  const onFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f || !f.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      trimLogo(reader.result).then((trimmed) => onSetLogo(block.id, trimmed));
    };
    reader.readAsDataURL(f);
    e.target.value = "";
  };
  return (
    <div>
      <HeaderBlock block={block} />
      <div className="mt-2 flex items-center gap-3">
        <span className="text-xs font-semibold text-stone-500">Client logo (cover, left):</span>
        {block.clientLogo ? (
          <img src={block.clientLogo} alt="Client logo"
               className="h-10 rounded border border-stone-200 bg-white p-1 object-contain" />
        ) : (
          <span className="text-xs text-stone-400">none</span>
        )}
        <label className="text-xs px-2 py-1 rounded-md border border-stone-200 text-stone-600 hover:bg-orange-50 hover:text-orange-700 cursor-pointer">
          {block.clientLogo ? "Replace" : "Upload logo"}
          <input type="file" accept="image/*" onChange={onFile} className="hidden" />
        </label>
        {block.clientLogo ? (
          <button type="button" onClick={() => onSetLogo(block.id, null)}
                  className="text-xs text-stone-400 hover:text-red-600">Remove</button>
        ) : null}
      </div>
    </div>
  );
}

function BlockFrame({ index, total, label, onUp, onDown, onDelete, onAddTextBelow, children }) {
  return (
    <div className="group relative rounded-xl border border-stone-200 bg-stone-50/40 p-2">
      <div className="flex items-center justify-between mb-1.5 px-1">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-stone-300">
          {label}
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

function EditableDoc({ version, blobs, canSend = false }) {
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

  useEffect(() => {
    let cancelled = false;
    api(`/reports/${version.id}/template-blocks`)
      .then((d) => !cancelled && setTemplateBlocks(d.blocks || []))
      .catch(() => !cancelled && setTemplateBlocks([]));
    return () => {
      cancelled = true;
    };
  }, [version.id]);

  const onDocChange = useCallback((id, doc) => {
    setBlocks((bs) => bs.map((b) => (b.id === id ? { ...b, doc } : b)));
  }, []);
  const onFocusEditor = useCallback((editor) => {
    activeEditorRef.current = editor;
  }, []);

  const rowsKey = (block) => (block.type === "backlinks_list" ? "items" : "rows");
  const setRowIncluded = useCallback((blockId, rowIndex, included) => {
    setBlocks((bs) =>
      bs.map((b) => {
        if (b.id !== blockId) return b;
        const key = rowsKey(b);
        const arr = (b[key] || []).map((r, i) => (i === rowIndex ? { ...r, included } : r));
        return { ...b, [key]: arr };
      })
    );
  }, []);
  const setRowsBulk = useCallback((blockId, mode) => {
    setBlocks((bs) =>
      bs.map((b) => {
        if (b.id !== blockId) return b;
        const key = rowsKey(b);
        const arr = (b[key] || []).map((r, i) => {
          const included = mode === "all" ? true : mode === "none" ? false : i < mode;
          return { ...r, included };
        });
        return { ...b, [key]: arr };
      })
    );
  }, []);

  const setClientLogo = useCallback((blockId, dataUri) => {
    setBlocks((bs) => bs.map((b) => (b.id === blockId ? { ...b, clientLogo: dataUri } : b)));
  }, []);

  const setBlockTitle = useCallback((blockId, value) => {
    setBlocks((bs) => bs.map((b) => (b.id === blockId ? { ...b, title: value } : b)));
  }, []);

  const setCellValue = useCallback((blockId, rowIndex, colKey, value) => {
    setBlocks((bs) =>
      bs.map((b) => {
        if (b.id !== blockId) return b;
        const col = (b.columns || []).find((c) => c.key === colKey);
        const isMetric = col && col.kind !== "dim";
        let next = value;
        if (isMetric) {
          const digits = String(value).replace(/[^0-9]/g, "");
          next = digits === "" ? null : Number(digits);
        }
        const rows = (b.rows || []).map((r, i) => {
          if (i !== rowIndex) return r;
          const cells = { ...(r.cells || {}), [colKey]: next };
          if (colKey === "current_rank" || colKey === "previous_rank") {
            const cur = cells.current_rank;
            const prev = cells.previous_rank;
            cells.rank_delta =
              cur === null || cur === undefined || prev === null || prev === undefined
                ? null
                : cur - prev;
          }
          return { ...r, cells };
        });
        return { ...b, rows };
      })
    );
  }, []);

  const setTargetValue = useCallback((blockId, colKey, fieldKey, value) => {
    setBlocks((bs) =>
      bs.map((b) => {
        if (b.id !== blockId) return b;
        const values = { ...(b.values || {}) };
        values[colKey] = { ...(values[colKey] || {}), [fieldKey]: value };
        return { ...b, values };
      })
    );
  }, []);
  const setTargetNotes = useCallback((blockId, value) => {
    setBlocks((bs) => bs.map((b) => (b.id === blockId ? { ...b, notes: value } : b)));
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
      throw e;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="w-full">
      <div className="sticky top-0 z-30 -mx-6 px-6 py-3 mb-3 flex flex-wrap items-center justify-between gap-3 bg-stone-100/90 backdrop-blur-sm border-b border-stone-200">
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
          <DownloadPdfButton
            versionId={version.id}
            periodKey={version.periodKey}
            projectName={version.content?.blocks?.find((b) => b.type === "report_header")?.projectName}
            label
            beforeDownload={save}
            onError={setSaveError}
          />
          <button onClick={() => save().catch(() => {})} disabled={saving} className={`${BTN_PRIMARY} px-3 py-1.5`}>
            {saving ? <LoaderCircle size={14} className="animate-spin" /> : <Save size={14} />} Save draft
          </button>
        </div>
      </div>

      <ErrorNote>{saveError}</ErrorNote>

      <p className="mb-3 text-sm text-stone-500">
        Reorder, delete, and add blocks; edit any text block (type <kbd className="px-1 rounded bg-stone-100 border border-stone-200">/</kbd> to insert data). Keyword ranks are editable here; every other data value is fixed. Edits apply to this report only.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_15rem] gap-4">
        <div className="min-w-0 space-y-3">
          {blocks.map((block, i) => {
            const isData = DATA_BLOCK_TYPES.has(block.type);
            const canSelectRows =
              block.type === "data_table" || block.type === "backlinks_list";
            const frameLabel = canSelectRows
              ? "Data · choose rows / move / delete"
              : isData
              ? "Data · move / delete only"
              : "Editable text";
            return (
              <BlockFrame
                key={block.id}
                index={i}
                total={blocks.length}
                label={frameLabel}
                onUp={() => move(i, -1)}
                onDown={() => move(i, 1)}
                onDelete={() => remove(i)}
                onAddTextBelow={() => addTextAt(i)}
              >
                {block.type !== "report_header" && (
                  <input
                    type="text"
                    value={block.title || ""}
                    onChange={(e) => setBlockTitle(block.id, e.target.value)}
                    placeholder="Section title"
                    className="w-full mb-2 bg-transparent text-base font-bold text-stone-900 font-display border-0 border-b border-transparent hover:border-stone-200 focus:border-orange-300 focus:outline-none px-0"
                  />
                )}
                {block.type === "report_header" ? (
                  <HeaderEditor block={block} onSetLogo={setClientLogo} />
                ) : block.type === "narrative" ? (
                  <NarrativeEditor
                    block={block}
                    BlobNode={BlobNode}
                    suggestion={suggestion}
                    onDocChange={onDocChange}
                    onFocusEditor={onFocusEditor}
                  />
                ) : block.type === "data_table" ? (
                  <DataTableBlock
                    block={block}
                    selectable
                    hideTitle
                    editable={block.id === EDITABLE_TABLE_ID}
                    onCellChange={(rowIndex, colKey, value) =>
                      setCellValue(block.id, rowIndex, colKey, value)
                    }
                    onToggleRow={(rowIndex, inc) => setRowIncluded(block.id, rowIndex, inc)}
                    onBulk={(mode) => setRowsBulk(block.id, mode)}
                  />
                ) : block.type === "backlinks_list" ? (
                  <BacklinksBlock
                    block={block}
                    selectable
                    hideTitle
                    onToggleRow={(rowIndex, inc) => setRowIncluded(block.id, rowIndex, inc)}
                    onBulk={(mode) => setRowsBulk(block.id, mode)}
                  />
                ) : block.type === "targets_grid" ? (
                  <TargetsGridEditor
                    block={block}
                    onSetValue={setTargetValue}
                  />
                ) : (
                  <ReadOnlyDataBlock block={block} hideTitle />
                )}
              </BlockFrame>
            );
          })}

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

        <div className="lg:sticky lg:top-4 self-start">
          <BlobPalette items={paletteItems} onInsert={insertBlob} />
          <p className="mt-2 text-[11px] text-stone-400">
            Click a field to insert it into the text block you last edited, or type
            <kbd className="mx-1 px-1 rounded bg-stone-100 border border-stone-200">/</kbd> in a text block.
          </p>
        </div>
      </div>

      <SuggestionMenu sugg={sugg} />
    </div>
  );
}
