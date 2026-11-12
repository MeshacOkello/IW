import { useEffect, useRef, useState } from "react";

export default function StdIn({ prompt, busy, error, onSubmit, onClose, returnFocusRef, fallbackFocusRef }) {
    const dialog = useRef(null);
    const input = useRef(null);
    const [text, setText] = useState("");

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
                    onChange={(event) => setText(event.target.value)} disabled={busy} />
                {error && <p role="alert">{error}</p>}
                <div className="stdin-actions">
                    <button type="submit" disabled={busy} title="Send text without a newline, then end input">Submit</button>
                </div>
            </form>
        </dialog>
    );
}
