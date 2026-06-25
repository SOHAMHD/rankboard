/* ════════════════════════════════════════════════════════════════════
   BLOB NODE — the atomic TipTap chip for an inserted data blob.

   Built on @tiptap/extension-mention so we inherit its ATOMIC inline node
   (deletes as one unit, cursor can't land mid-chip) and its suggestion plugin
   (the "/" trigger; configured by the editor page). A chip stores only
   { name, kind, format, label } — NEVER the resolved value — so resolution
   stays dynamic against the frozen data and reopening restores the chip.

   The chip's React node view shows the blob's LABEL (the field name) in the
   editing surface — not the raw value (the live preview shows values). Clicking
   a chip (when the editor is editable) opens a per-chip FORMAT picker whose
   options are computed from the blob's real value.
   ════════════════════════════════════════════════════════════════════ */
import { useEffect, useRef, useState } from "react";
import Mention from "@tiptap/extension-mention";
import { mergeAttributes } from "@tiptap/core";
import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import { AlertTriangle } from "lucide-react";
import { applyFormat, formatOptions, chipLabel } from "./blobFormats";

const CHIP_OK =
  "inline-flex items-center gap-1 rounded-md border border-orange-200 bg-orange-50 px-1.5 py-0.5 text-sm font-medium text-orange-700 align-baseline select-none";
const CHIP_BROKEN =
  "inline-flex items-center gap-1 rounded-md border border-red-200 bg-red-50 px-1.5 py-0.5 text-sm font-medium text-red-700 align-baseline select-none";

// The React node view. Closes over the resolved-blobs map (name -> blob) so it
// can resolve + format without any external lookup or context plumbing.
function makeChipView(blobsByName) {
  return function BlobChipView({ node, updateAttributes, editor }) {
    const { name, kind, format, label } = node.attrs;
    const blob = blobsByName.get(name);
    const resolved = blob ? applyFormat(blob, kind, format) : null;
    const broken = !blob || resolved === null;
    const editable = editor.isEditable;

    const [open, setOpen] = useState(false);
    const ref = useRef(null);
    useEffect(() => {
      if (!open) return undefined;
      const onDoc = (e) => {
        if (ref.current && !ref.current.contains(e.target)) setOpen(false);
      };
      const onKey = (e) => e.key === "Escape" && setOpen(false);
      document.addEventListener("mousedown", onDoc);
      document.addEventListener("keydown", onKey);
      return () => {
        document.removeEventListener("mousedown", onDoc);
        document.removeEventListener("keydown", onKey);
      };
    }, [open]);

    const text = chipLabel(blob, kind, label);
    const options = blob ? formatOptions(blob, kind) : [];

    return (
      <NodeViewWrapper as="span" className="inline-block align-baseline">
        <span ref={ref} className="relative inline-block" contentEditable={false}>
          <button
            type="button"
            onClick={() => editable && blob && setOpen((o) => !o)}
            className={`${broken ? CHIP_BROKEN : CHIP_OK} ${editable && blob ? "cursor-pointer hover:brightness-95" : "cursor-default"}`}
            title={broken ? "This data couldn't be resolved from the frozen report." : `${text}${resolved ? ` → ${resolved}` : ""}`}
          >
            {broken && <AlertTriangle size={11} />}
            <span>{text}</span>
          </button>

          {open && blob && (
            <span
              contentEditable={false}
              className="absolute left-0 top-full z-30 mt-1 block w-56 overflow-hidden rounded-lg border border-stone-200 bg-white shadow-xl"
            >
              <span className="block border-b border-stone-100 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                Format
              </span>
              {options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  onClick={() => {
                    updateAttributes({ format: o.id });
                    setOpen(false);
                  }}
                  className={`flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm ${
                    o.id === format ? "bg-orange-50 text-orange-700" : "text-stone-700 hover:bg-stone-100"
                  }`}
                >
                  <span className="text-xs text-stone-500">{o.name}</span>
                  <span className="font-data font-medium">{o.sample}</span>
                </button>
              ))}
            </span>
          )}
        </span>
      </NodeViewWrapper>
    );
  };
}

/** Build the atomic "blob" node bound to a resolved-blobs map. Recreate it when
 *  the map changes (frozen per version, so effectively once). The suggestion
 *  config is supplied separately by the page via `.configure({ suggestion })`. */
export function createBlobNode(blobsByName) {
  return Mention.extend({
    name: "blob",

    addAttributes() {
      // Each attribute round-trips to a data-* attribute. renderHTML receives the
      // full attrs object, so we capture each attribute's KEY in the closure.
      const make = (key, dataName, def) => ({
        default: def,
        parseHTML: (el) => el.getAttribute(dataName) ?? def,
        renderHTML: (attrs) =>
          attrs[key] == null || attrs[key] === "" ? {} : { [dataName]: attrs[key] },
      });
      return {
        name: make("name", "data-blob-name", null),
        kind: make("kind", "data-blob-kind", "value"),
        format: make("format", "data-blob-format", null),
        label: make("label", "data-blob-label", ""),
      };
    },

    parseHTML() {
      return [{ tag: "span[data-blob-name]" }];
    },

    renderHTML({ HTMLAttributes }) {
      return ["span", mergeAttributes({ "data-type": "blob" }, HTMLAttributes)];
    },

    // Plain-text fallback (copy/paste, getText) — never the resolved value.
    renderText({ node }) {
      return `{{${node.attrs.name || ""}${node.attrs.kind === "delta" ? ":delta" : ""}}}`;
    },

    addNodeView() {
      return ReactNodeViewRenderer(makeChipView(blobsByName));
    },
  });
}
