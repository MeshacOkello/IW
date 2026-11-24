import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { indentEdit } from "../editorIndent";
import { highlightLine } from "../highlight";

export default function CodeEditor({
    assemblyCode,
    setAssemblyCode,
    activeLine,
    upcomingLine = null,
    breakpoints = new Set(),
    pickingBreakpoint = false,
    onPickBreakpoint,
    onCancelPicking,
    notice = null,
    darkTheme = false,
    onDarkThemeChange,
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

    // Choosing a breakpoint: the line numbers become buttons. Focus starts on
    // the line in view, and moving it scrolls the editor rather than the
    // gutter, which only ever follows the textarea.
    const focusGutterLine = useCallback((line) => {
        const button = gutterRef.current?.querySelector(`[data-line="${line}"]`);
        if (!button) return;
        button.focus({ preventScroll: true });
        revealLine(line);
    }, [revealLine]);

    useEffect(() => {
        if (!pickingBreakpoint) return;
        const textarea = textareaRef.current;
        const lineHeight = parseFloat(getComputedStyle(textarea).lineHeight) || 22;
        const firstVisible = Math.floor(textarea.scrollTop / lineHeight) + 1;
        const start = activeLineRef.current ?? firstVisible;
        focusGutterLine(Math.min(start, textarea.value.split("\n").length));
    }, [pickingBreakpoint, focusGutterLine]);

    // While choosing, a click anywhere along a line picks it, and the line
    // under the pointer is tinted first so the choice is clear.
    const [hoverLine, setHoverLine] = useState(null);
    const pickHover = pickingBreakpoint ? hoverLine : null;

    function lineAtPointer(event) {
        const textarea = textareaRef.current;
        const styles = getComputedStyle(textarea);
        const lineHeight = parseFloat(styles.lineHeight);
        const y = event.clientY - textarea.getBoundingClientRect().top
            - parseFloat(styles.paddingTop) + textarea.scrollTop;
        const line = Math.floor(y / lineHeight) + 1;
        return line >= 1 && line <= lines.length ? line : null;
    }

    function handleSurfaceMouseDown(event) {
        if (!pickingBreakpoint || event.button !== 0) return;
        event.preventDefault();      // no caret, no selection: this is a pick
        const line = lineAtPointer(event);
        if (line !== null) onPickBreakpoint?.(line);
    }

    function handleGutterKey(event, line) {
        const moves = { ArrowDown: 1, ArrowUp: -1, PageDown: 10, PageUp: -10 };
        if (event.key === "Escape") {
            event.preventDefault();
            onCancelPicking?.();
        } else if (moves[event.key] !== undefined) {
            event.preventDefault();
            focusGutterLine(Math.max(1, Math.min(lines.length, line + moves[event.key])));
        } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            focusGutterLine(event.key === "Home" ? 1 : lines.length);
        }
    }

    useEffect(() => {
        const observer = new ResizeObserver(() => {
            measureScrollbars();
            revealLine(activeLineRef.current);
        });
        observer.observe(textareaRef.current);
        return () => observer.disconnect();
    }, [measureScrollbars, revealLine]);

    function gutterClass(line) {
        return [
            activeLine === line && "active-line-number",
            upcomingLine === line && "upcoming-line-number",
            breakpoints.has(line) && "has-breakpoint",
            pickHover === line && "breakpoint-hover",
        ].filter(Boolean).join(" ") || undefined;
    }

    return (
        <div className={`code-editor${pickingBreakpoint ? " code-editor-picking" : ""}`}>
            {/* A fixed row above the code: what to do while choosing a
                breakpoint, or where execution is paused. Always the same
                height, so the editor never shifts when it changes. */}
            <p className="editor-status" id="breakpoint-hint" role="status">
                {pickingBreakpoint ? "Click a line to set or clear a breakpoint." : notice}
            </p>
            <div className="editor-container" ref={containerRef}>
                {/* The theme switch floats in the code's top-right corner;
                    clicks around it still reach the code. */}
                <div className="editor-overlay">
                {onDarkThemeChange && (
                    <label className="theme-switch editor-theme-switch">
                        Dark editor
                        <input
                            type="checkbox"
                            role="switch"
                            checked={darkTheme}
                            onChange={(event) => onDarkThemeChange(event.target.checked)}
                        />
                        <span className="switch-track" aria-hidden="true" />
                    </label>
                )}
                </div>
                <div
                    className={`editor-gutter${pickingBreakpoint ? " gutter-picking" : ""}`}
                    ref={gutterRef}
                    role={pickingBreakpoint ? "group" : undefined}
                    aria-label={pickingBreakpoint ? "Line numbers" : undefined}
                    aria-describedby={pickingBreakpoint ? "breakpoint-hint" : undefined}
                    aria-hidden={pickingBreakpoint ? undefined : "true"}
                >
                    {lines.map((_, index) => {
                        const line = index + 1;
                        return pickingBreakpoint ? (
                            <button
                                key={index}
                                type="button"
                                data-line={line}
                                className={gutterClass(line)}
                                tabIndex={-1}
                                aria-pressed={breakpoints.has(line)}
                                aria-label={`Toggle breakpoint on line ${line}`}
                                onClick={() => onPickBreakpoint?.(line)}
                                onMouseEnter={() => setHoverLine(line)}
                                onMouseLeave={() => setHoverLine(null)}
                                onKeyDown={(event) => handleGutterKey(event, line)}
                            >
                                {line}
                            </button>
                        ) : (
                            <span key={index} className={gutterClass(line)}>{line}</span>
                        );
                    })}
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
                                className={[
                                    activeLine === index + 1 && "active-line",
                                    upcomingLine === index + 1 && "upcoming-line",
                                    breakpoints.has(index + 1) && "breakpoint-line",
                                    pickHover === index + 1 && "breakpoint-hover",
                                ].filter(Boolean).join(" ")}
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
                        onMouseDown={handleSurfaceMouseDown}
                        onMouseMove={pickingBreakpoint ? (event) => setHoverLine(lineAtPointer(event)) : undefined}
                        onMouseLeave={() => setHoverLine(null)}
                        wrap="off"
                        spellCheck={false}
                        aria-label="Assembly code"
                    />
                </div>
            </div>
        </div>
    );
}
