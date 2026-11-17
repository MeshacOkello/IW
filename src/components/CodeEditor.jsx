import { useLayoutEffect, useRef } from "react";
import { indentEdit } from "../editorIndent";

export default function CodeEditor({
    assemblyCode,
    setAssemblyCode,
    activeLine,
}) {
    const textareaRef = useRef(null);
    const backdropRef = useRef(null);

    function syncScroll() {
        const textarea = textareaRef.current;
        const backdrop = backdropRef.current;

        if (!textarea || !backdrop) return;

        backdrop.scrollTop = textarea.scrollTop;
        backdrop.scrollLeft = textarea.scrollLeft;
    }

    // Replace a range in place, through the browser's own editing command so
    // the change joins the textarea's undo history like any typed edit. The
    // input event it fires is what keeps React's value in step.
    function replaceRange(textarea, start, end, text) {
        textarea.setSelectionRange(start, end);
        if (document.execCommand("insertText", false, text)) return;
        const { value } = textarea;
        const setValue = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype, "value").set;
        setValue.call(textarea, value.slice(0, start) + text + value.slice(end));
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function handleKeyDown(event) {
        // Tab types indentation here rather than leaving the editor, so
        // Escape is the way out for anyone working from the keyboard.
        if (event.key === "Escape") {
            event.currentTarget.blur();
            return;
        }
        if (event.key !== "Tab" || event.altKey || event.ctrlKey || event.metaKey) return;
        event.preventDefault();

        const textarea = event.currentTarget;
        const edit = indentEdit({
            value: textarea.value,
            selectionStart: textarea.selectionStart,
            selectionEnd: textarea.selectionEnd,
            outdent: event.shiftKey,
        });
        if (!edit) return;

        replaceRange(textarea, edit.start, edit.end, edit.text);
        if (edit.caret !== undefined) {
            textarea.setSelectionRange(edit.caret, edit.caret);
        } else {
            textarea.setSelectionRange(edit.selectionStart, edit.selectionEnd);
        }
    }

    useLayoutEffect(() => {
        const textarea = textareaRef.current;
        if (!textarea || activeLine == null) return;

        const styles = getComputedStyle(textarea);
        const lineHeight = parseFloat(styles.lineHeight);
        const paddingTop = parseFloat(styles.paddingTop);
        const paddingBottom = parseFloat(styles.paddingBottom);

        const lineTop = paddingTop + (activeLine - 1) * lineHeight;
        const lineBottom = lineTop + lineHeight;

        const visibleTop = textarea.scrollTop + paddingTop;
        const visibleBottom =
            textarea.scrollTop + textarea.clientHeight - paddingBottom;

        if (lineTop < visibleTop || lineBottom > visibleBottom) {
            textarea.scrollTop = Math.max(
                0,
                lineTop - (textarea.clientHeight - lineHeight) / 2
            );
        }

        syncScroll();
    }, [activeLine, assemblyCode]);

    return (
        <div className="code-editor">
            <h4>Assembly Code</h4>

            <div className="editor-container">
                <pre
                    className="editor-backdrop"
                    ref={backdropRef}
                    aria-hidden="true"
                >
                    {assemblyCode.split("\n").map((line, index) => (
                        <span
                            key={index}
                            className={
                                activeLine === index + 1 ? "active-line" : ""
                            }
                        >
                            {line || " "}
                        </span>
                    ))}
                </pre>

                <textarea
                    ref={textareaRef}
                    className="assembly-input"
                    value={assemblyCode}
                    onChange={(event) => setAssemblyCode(event.target.value)}
                    onKeyDown={handleKeyDown}
                    onScroll={syncScroll}
                    wrap="off"
                    spellCheck={false}
                    aria-label="Assembly code"
                />
            </div>
        </div>
    );
}
