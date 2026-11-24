import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { indentEdit } from "../editorIndent";
import { highlightLine } from "../highlight";

export default function CodeEditor({
    assemblyCode,
    setAssemblyCode,
    activeLine,
    predicting = false,
}) {
    const textareaRef = useRef(null);
    const backdropRef = useRef(null);
    const gutterRef = useRef(null);
    const containerRef = useRef(null);
    const lines = assemblyCode.split("\n");

    function syncScroll() {
        const textarea = textareaRef.current;
        const backdrop = backdropRef.current;
        const gutter = gutterRef.current;

        if (!textarea || !backdrop) return;

        backdrop.scrollTop = textarea.scrollTop;
        backdrop.scrollLeft = textarea.scrollLeft;
        if (gutter) gutter.scrollTop = textarea.scrollTop;
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

    // The textarea's scrollbars shrink its client area, which lets it scroll
    // further than the backdrop and gutter beside it. Their size is passed to
    // the stylesheet, which pads those two by the same amount. Scrollbars
    // come and go with the text as well as with the editor's size.
    const measureScrollbars = useCallback(() => {
        const textarea = textareaRef.current;
        const container = containerRef.current;
        if (!textarea || !container) return;
        container.style.setProperty("--editor-scrollbar-x", `${textarea.offsetHeight - textarea.clientHeight}px`);
        container.style.setProperty("--editor-scrollbar-y", `${textarea.offsetWidth - textarea.clientWidth}px`);
        syncScroll();
    }, []);

    useLayoutEffect(measureScrollbars, [assemblyCode, measureScrollbars]);

    // Bring the executed line into view if it is outside the editor.
    const revealLine = useCallback((line) => {
        const textarea = textareaRef.current;
        if (!textarea || line == null) return;

        const styles = getComputedStyle(textarea);
        const lineHeight = parseFloat(styles.lineHeight);
        const paddingTop = parseFloat(styles.paddingTop);
        const paddingBottom = parseFloat(styles.paddingBottom);

        const lineTop = paddingTop + (line - 1) * lineHeight;
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
    }, []);

    useLayoutEffect(() => revealLine(activeLine), [activeLine, assemblyCode, revealLine]);

    // The editor's height follows the window, so a resize can leave the
    // executed line out of view as well as change the scrollbars.
    const activeLineRef = useRef(activeLine);
    useEffect(() => {
        activeLineRef.current = activeLine;
    });

    useEffect(() => {
        const observer = new ResizeObserver(() => {
            measureScrollbars();
            revealLine(activeLineRef.current);
        });
        observer.observe(textareaRef.current);
        return () => observer.disconnect();
    }, [measureScrollbars, revealLine]);

    return (
        <div className={`code-editor${predicting ? " code-editor-predicting" : ""}`}>
            <div className="editor-container" ref={containerRef}>
                <div className="editor-gutter" ref={gutterRef} aria-hidden="true">
                    {lines.map((_, index) => (
                        <span
                            key={index}
                            className={activeLine === index + 1 ? "active-line-number" : ""}
                        >
                            {index + 1}
                        </span>
                    ))}
                </div>

                <div className="editor-surface">
                    {/* The coloured text lives here; the textarea above it is
                        transparent apart from its caret and selection. */}
                    <pre
                        className="editor-backdrop"
                        ref={backdropRef}
                        aria-hidden="true"
                    >
                        {lines.map((line, index) => (
                            <span
                                key={index}
                                className={
                                    activeLine === index + 1 ? "active-line" : ""
                                }
                            >
                                {line === ""
                                    ? " "
                                    : highlightLine(line).map((token, position) => (
                                        <span key={position} className={`tok-${token.kind}`}>
                                            {token.text}
                                        </span>
                                    ))}
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
        </div>
    );
}
