import { useEffect, useRef, useState } from "react";
import { parseStepInput } from "../timeline";

function PencilIcon() {
    return (
        <svg className="icon" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" focusable="false">
            <path d="M4 20h4L19 9l-4-4L4 16z M13.5 6.5l4 4" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}

// "Step X of Y", where X opens a small jump card: type a step and see which
// instruction it lands after before going there, or pick the start, the end
// or a breakpoint stop ahead.
export default function StepJump({ currentStep, totalSteps, disabled, onJump, summarize, breakpointStops = [] }) {
    const [draft, setDraft] = useState(null);
    const editButton = useRef(null);
    const input = useRef(null);
    const editing = draft !== null && !disabled;

    useEffect(() => {
        if (editing) input.current?.select();
    }, [editing]);

    function close(returnFocus = true) {
        setDraft(null);
        if (returnFocus) requestAnimationFrame(() => editButton.current?.focus());
    }

    function go(step) {
        onJump(step);
        close();
    }

    const parsed = editing ? parseStepInput(draft, totalSteps) : null;
    const preview = parsed?.step !== undefined ? summarize(parsed.step) : null;
    const ahead = breakpointStops.filter((step) => step > currentStep).slice(0, 5);

    if (!editing) {
        return (
            <span className="step-counter">
                Step{" "}
                <button
                    ref={editButton}
                    type="button"
                    className="step-edit"
                    disabled={disabled}
                    onClick={() => setDraft(String(currentStep))}
                    aria-label={`Edit step, now ${currentStep} of ${totalSteps}`}
                    title="Edit step: jump to any recorded step"
                >
                    {currentStep}<PencilIcon />
                </button>
                {" "}of {totalSteps}
            </span>
        );
    }

    return (
        <span
            className="step-counter step-jump"
            onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) close(false);
            }}
        >
            Step{" "}
            <input
                ref={input}
                className="step-input"
                type="number"
                inputMode="numeric"
                min={0}
                max={totalSteps}
                value={draft}
                aria-label={`Go to step, 0 to ${totalSteps}`}
                aria-invalid={parsed.error ? true : undefined}
                aria-describedby="step-jump-preview"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                    if (event.key === "Enter" && parsed.step !== undefined) {
                        event.preventDefault();
                        go(parsed.step);
                    } else if (event.key === "Escape") {
                        event.preventDefault();
                        close();
                    }
                }}
            />
            {" "}of {totalSteps}

            <span className="step-jump-card" role="group" aria-label="Jump to step">
                <span className="step-jump-preview" id="step-jump-preview" aria-live="polite">
                    {parsed.error ? <span className="step-jump-error">{parsed.error}</span>
                        : preview.line === null ? preview.text
                        : <>After line {preview.line} · <code>{preview.text}</code></>}
                </span>
                <span className="step-jump-chips">
                    <button type="button" onClick={() => go(0)}>Start</button>
                    <button type="button" onClick={() => go(totalSteps)}>End</button>
                    {ahead.map((step) => {
                        const line = summarize(step + 1).line;
                        return (
                            <button type="button" key={step} className="step-chip-breakpoint"
                                onClick={() => go(step)} title={`Step ${step}, just before line ${line} runs`}>
                                {step}
                                <span className="visually-hidden">: before breakpoint on line {line}</span>
                            </button>
                        );
                    })}
                </span>
                <span className="step-jump-actions">
                    <span className="step-jump-keys"><kbd>Enter</kbd> go · <kbd>Esc</kbd> cancel</span>
                    <button type="button" className="primary" disabled={parsed.step === undefined}
                        onClick={() => go(parsed.step)}>Go</button>
                </span>
            </span>
        </span>
    );
}
