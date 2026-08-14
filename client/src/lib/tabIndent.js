import { Extension } from "@tiptap/core";

const INDENT = "    ";

export const TabIndent = Extension.create({
  name: "tabIndent",

  addKeyboardShortcuts() {
    return {
      // Only swallow Tab when there is a list item to indent. insertContent()
      // always reports success, so returning it meant Tab never propagated and
      // the editor became a keyboard trap — no way out of it without a mouse
      // (WCAG 2.1.2). Outside a list, Tab now does what it does everywhere else
      // and moves focus to the next control.
      Tab: () => {
        if (this.editor.can().sinkListItem("listItem")) {
          return this.editor.commands.sinkListItem("listItem");
        }
        return false;
      },

      "Shift-Tab": () => {
        if (this.editor.can().liftListItem("listItem")) {
          return this.editor.commands.liftListItem("listItem");
        }
        const { state } = this.editor;
        const { from, empty } = state.selection;
        if (empty && from > INDENT.length) {
          const before = state.doc.textBetween(from - INDENT.length, from, "\n", "\n");
          if (before === INDENT) {
            return this.editor.commands.deleteRange({ from: from - INDENT.length, to: from });
          }
        }
        return false;
      },
    };
  },
});

export default TabIndent;
