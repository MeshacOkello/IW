import { useEffect, useRef } from "react";

// Asked before an example would overwrite code the student has written.
export default function ReplaceCodeDialog({ title, onConfirm, onCancel, returnFocusRef }) {
    const dialog = useRef(null);
    const cancel = useRef(null);

    useEffect(() => {
        const element = dialog.current;
        const opener = returnFocusRef?.current;
        element.showModal();
        // The safe choice has focus, so Enter never discards work by accident.
        cancel.current.focus();
        return () => {
            element.close();
            if (opener?.isConnected) opener.focus();
        };
    }, [returnFocusRef]);

    return (
        <dialog className="confirm-dialog" ref={dialog} aria-labelledby="replace-title"
            aria-describedby="replace-description"
            onCancel={(event) => { event.preventDefault(); onCancel(); }}>
            <h2 id="replace-title">Replace your code?</h2>
            <p id="replace-description">
                The editor has code you have written. Opening “{title}” replaces it, and this
                cannot be undone. Copy your code first if you want to keep it.
            </p>
            <div className="confirm-actions">
                <button type="button" ref={cancel} onClick={onCancel}>Keep my code</button>
                <button type="button" className="danger" onClick={onConfirm}>Replace code</button>
            </div>
        </dialog>
    );
}
