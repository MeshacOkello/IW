import { useLayoutEffect, useRef } from "react";

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
                    onScroll={syncScroll}
                    wrap="off"
                    spellCheck={false}
                    aria-label="Assembly code"
                />
            </div>
        </div>
    );
}
