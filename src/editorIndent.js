// VS Code's Tab behaviour for a plain textarea: Tab indents to the next tab
// stop, Shift+Tab outdents, and a selection spanning lines shifts every line
// it touches. Kept apart from the component so it can be tested directly.

export const INDENT = "    ";
const ONE_INDENT = new RegExp(`^(?:\\t| {1,${INDENT.length}})`);

/** Work out the edit a Tab or Shift+Tab should make.
 *
 * Returns the range to replace, the text to put there, and where the
 * selection should land, or null when the key should be left alone.
 */
export function indentEdit({ value, selectionStart, selectionEnd, outdent }) {
    const lineStart = value.lastIndexOf("\n", selectionStart - 1) + 1;
    // Whether whole lines are involved is decided by the selection as made;
    // `reach` only trims a trailing newline so the line below is left alone.
    const spansLines = value.slice(selectionStart, selectionEnd).includes("\n");
    const reach = selectionEnd > selectionStart && value[selectionEnd - 1] === "\n"
        ? selectionEnd - 1
        : selectionEnd;

    if (!outdent && !spansLines) {
        // Indent to the next tab stop, counting from the start of the line.
        const width = INDENT.length - ((selectionStart - lineStart) % INDENT.length);
        const caret = selectionStart + width;
        return { start: selectionStart, end: selectionEnd, text: " ".repeat(width), caret };
    }

    const lineEnd = value.indexOf("\n", reach);
    const blockEnd = lineEnd === -1 ? value.length : lineEnd;
    const lines = value.slice(lineStart, blockEnd).split("\n");

    let firstShift = 0;
    let totalShift = 0;
    const shifted = lines.map((line, index) => {
        const updated = outdent ? line.replace(ONE_INDENT, "") : INDENT + line;
        const shift = updated.length - line.length;
        if (index === 0) firstShift = shift;
        totalShift += shift;
        return updated;
    });

    if (totalShift === 0) return null;   // nothing to outdent
    return {
        start: lineStart,
        end: blockEnd,
        text: shifted.join("\n"),
        // A selection anchored at the margin stays there, so the shifted text
        // stays inside it and Tab can be pressed again on the same block.
        selectionStart: selectionStart === lineStart
            ? lineStart
            : Math.max(lineStart, selectionStart + firstShift),
        selectionEnd: Math.max(lineStart, selectionEnd + totalShift),
    };
}
