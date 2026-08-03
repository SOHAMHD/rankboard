import { Extension } from "@tiptap/core";

const INDENT = "    ";

export const TabIndent = Extension.create({
  name: "tabIndent",

  addKeyboardShortcuts() {
    return {
      Tab: () => {
        if (this.editor.can().sinkListItem("listItem")) {
          return this.editor.commands.sinkListItem("listItem");
        }
        return this.editor.commands.insertContent(INDENT);
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
