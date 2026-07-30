/* ════════════════════════════════════════════════════════════════════
   TAB INDENT — make Tab insert an indent in the report's TipTap editors.

   Two separate reasons Tab did nothing before:

   1. Nothing bound it. Tab is the browser's "move focus to the next control",
      so the keystroke left the editor before ProseMirror ever saw it.

   2. Even a literal tab character wouldn't have shown. The rendered report uses
      normal HTML whitespace handling (white-space: normal), which collapses
      "\t" and runs of spaces down to ONE space — on screen AND in the PDF. So
      the indent has to be built from NON-BREAKING spaces to survive.

   Lists keep their normal behaviour: inside a list item Tab nests and Shift-Tab
   un-nests, which is what StarterKit's ListItem already does and what users
   expect. Only outside a list does Tab insert whitespace.

   TRADE-OFF worth knowing: capturing Tab means keyboard users can no longer Tab
   out of the editor to the next control — the same trade-off Google Docs and
   Notion make. Shift-Tab still escapes from a non-list paragraph because the
   handler returns false there, letting the browser's default focus move happen.
   ════════════════════════════════════════════════════════════════════ */
import { Extension } from "@tiptap/core";

// Four non-breaking spaces ≈ one tab stop at the report's body size. U+00A0 is
// used (not U+0009 or plain spaces) precisely because it is NOT collapsed.
const INDENT = "    ";

export const TabIndent = Extension.create({
  name: "tabIndent",

  addKeyboardShortcuts() {
    return {
      Tab: () => {
        // In a list, defer to the standard nest action rather than jamming
        // spaces into the item's text.
        if (this.editor.can().sinkListItem("listItem")) {
          return this.editor.commands.sinkListItem("listItem");
        }
        // Returning true is what stops the browser moving focus.
        return this.editor.commands.insertContent(INDENT);
      },

      "Shift-Tab": () => {
        if (this.editor.can().liftListItem("listItem")) {
          return this.editor.commands.liftListItem("listItem");
        }
        // Remove one indent's worth if the caret sits just after one, so Tab is
        // undoable with the key most people try first.
        const { state } = this.editor;
        const { from, empty } = state.selection;
        if (empty && from > INDENT.length) {
          const before = state.doc.textBetween(from - INDENT.length, from, "\n", "\n");
          if (before === INDENT) {
            return this.editor.commands.deleteRange({ from: from - INDENT.length, to: from });
          }
        }
        // Nothing to outdent — let the browser move focus out of the editor.
        return false;
      },
    };
  },
});

export default TabIndent;
