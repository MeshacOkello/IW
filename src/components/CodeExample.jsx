import { useEffect, useRef, useState } from "react";
import { highlightLine } from "../highlight";
import Icon from "./Icon";

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        // The clipboard API is unavailable outside a secure context.
        const area = document.createElement("textarea");
        area.value = text;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.append(area);
        area.select();
        const copied = document.execCommand("copy");
        area.remove();
        return copied;
    }
}

// A program drawn with the editor's own colours and line numbers.
export function CodeBlock({ source, label }) {
    const lines = source.replace(/\n$/, "").split("\n");
    return (
        <pre className="code-block" tabIndex={0} aria-label={label}>
            <code>
                {lines.map((line, index) => (
                    <span className="code-line" key={index}>
                        <span className="code-line-number" aria-hidden="true">{index + 1}</span>
                        <span className="code-line-text">
                            {line === "" ? " " : highlightLine(line).map((token, position) => (
                                <span key={position} className={`tok-${token.kind}`}>{token.text}</span>
                            ))}
                        </span>
                    </span>
                ))}
            </code>
        </pre>
    );
}

function Expected({ parts }) {
    return parts.map((part, index) => (
        <span key={index}>
            {index > 0 && " "}
            {part.code ? <code className="result-chip">{part.code}</code> : part.text}
        </span>
    ));
}

export default function CodeExample({ example, onOpen }) {
    const [copyState, setCopyState] = useState(null);
    const timer = useRef(null);
    const titleId = `example-${example.id}-title`;

    useEffect(() => () => clearTimeout(timer.current), []);

    async function copy() {
        const copied = await copyText(example.source);
        setCopyState(copied ? "copied" : "failed");
        clearTimeout(timer.current);
        timer.current = setTimeout(() => setCopyState(null), 2500);
    }

    const lines = example.source.trimEnd().split("\n");
    const long = lines.length > 16;
    const excerpt = example.excerpt ?? lines.filter(line => line.trim() && !line.trim().startsWith("//")).slice(0, 8).join("\n");

    return (
        <article className={`example-card${example.intentionalError ? " example-error" : ""}`}
            aria-labelledby={titleId}>
            <header className="example-head">
                {example.intentionalError && <p className="example-flag">Intentional error</p>}
                <h3 id={titleId}>{example.title}</h3>
                <p className="example-objective">{example.objective}</p>
            </header>

            {long ? <>
                <p className="excerpt-label">Excerpt</p>
                <CodeBlock source={excerpt} label={`${example.title} excerpt`} />
                <details className="full-code">
                    <summary>Full program ({lines.length} lines)</summary>
                    <CodeBlock source={example.source} label={`${example.title} full program`} />
                </details>
            </> : <CodeBlock source={example.source} label={`${example.title} program`} />}

            <p className="example-expected">
                <strong>Expected result:</strong> <Expected parts={example.expected} />
            </p>

            <div className="example-actions">
                {/* Every card has the same two buttons, so each names its example
                    for a screen reader moving between them. */}
                <button type="button" className="primary" aria-describedby={titleId}
                    onClick={(event) => onOpen(example, event.currentTarget)}>
                    Open in Visualizer
                </button>
                <button type="button" aria-describedby={titleId} onClick={copy}>
                    <Icon name={copyState === "copied" ? "check" : "copy"} />
                    {copyState === "copied" ? "Copied" : "Copy code"}
                </button>
                <span className="example-copy-status" role="status">
                    {copyState === "copied" && <span className="visually-hidden">Code copied to the clipboard.</span>}
                    {copyState === "failed" && "Copy was blocked. Select the code and copy it instead."}
                </span>
            </div>
        </article>
    );
}
