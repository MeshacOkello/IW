import { useEffect, useRef, useState } from "react";
import ErrorMessage from "./ErrorMessage";

export default function StdIn({ prompt, busy, error, formats, onSubmit, onClose, returnFocusRef, fallbackFocusRef }) {
    const dialog = useRef(null);
    const input = useRef(null);
    const [text, setText] = useState("");
    // Tab types a tab character until Escape releases it; the next Tab then
    // leaves for Submit. Focusing the textarea again restores tab typing.
    const tabReleased = useRef(false);

    useEffect(() => {
        const element = dialog.current;
        const opener = returnFocusRef.current;
        const next = fallbackFocusRef.current;
        element.showModal();
        input.current.focus();
        return () => {
            element.close();
            const target = opener?.isConnected && !opener.disabled ? opener
                : next && !next.disabled ? next
                : next?.closest('.execution-controls')?.querySelector('button:not(:disabled)');
            target?.focus();
        };
    }, [returnFocusRef, fallbackFocusRef]);

    function handleKeyDown(event) {
        if (event.key === "Escape" && !tabReleased.current) {
            // The first Escape only releases Tab; it does not close the dialog.
            event.preventDefault();
            event.stopPropagation();
            tabReleased.current = true;
            return;
        }
        if (event.key !== "Tab" || tabReleased.current || event.shiftKey
            || event.altKey || event.ctrlKey || event.metaKey) return;
        event.preventDefault();
        const textarea = event.currentTarget;
        // Through the browser's editing command, so the tab replaces any
        // selection and joins the undo history like typed text.
        if (!document.execCommand("insertText", false, "\t")) {
            const { selectionStart: start, selectionEnd: end, value } = textarea;
            Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")
                .set.call(textarea, value.slice(0, start) + "\t" + value.slice(end));
            textarea.setSelectionRange(start + 1, start + 1);
            textarea.dispatchEvent(new Event("input", { bubbles: true }));
        }
    }

    function submit(event) {
        event.preventDefault();
        if (!busy) onSubmit({ text, eof: true });
    }

    return (
        <dialog className="stdin-dialog" ref={dialog} aria-labelledby="stdin-title"
            onCancel={(event) => { event.preventDefault(); onClose(); }}>
            <form onSubmit={submit} aria-busy={busy}>
                <h3 id="stdin-title">{prompt}</h3>
                <label className="visually-hidden" htmlFor="stdin-text">Program input</label>
                <textarea id="stdin-text" ref={input} value={text} rows={2}
                    aria-describedby="stdin-tab-help"
                    onChange={(event) => setText(event.target.value)}
                    onKeyDown={handleKeyDown}
                    onFocus={() => { tabReleased.current = false; }}
                    disabled={busy} />
                <p className="visually-hidden" id="stdin-tab-help">
                    Tab types a tab character. Press Escape, then Tab, to move to Submit.
                </p>
                {error && <ErrorMessage error={error} formats={formats} />}
                <div className="stdin-actions">
                    <button type="submit" disabled={busy} title="Send text without a newline, then end input">Submit</button>
                </div>
            </form>
        </dialog>
    );
}
