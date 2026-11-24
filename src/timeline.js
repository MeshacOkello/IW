// Breakpoints and step jumps, read straight from the recorded history.
//
// The editor highlights the instruction that produced the selected step, so
// the state at step s is the state *after* executed_lines[s]. A breakpoint
// stops before its line runs: at the step whose *next* instruction is on a
// breakpoint line. That line is drawn as "about to run".

// True when stopping at `step` leaves a breakpoint line about to run.
export function isBreakpointStop(history, step, breakpoints) {
    if (!history || breakpoints.size === 0) return false;
    const upcoming = history.executed_lines?.[step + 1];
    return upcoming != null && breakpoints.has(upcoming);
}

// The first stop after `fromStep`, or null when none is recorded yet. The
// current step never counts, so continuing from a breakpoint moves past it.
// Only recorded steps are read: after input extends the history, calling
// again finds stops in the new steps.
export function nextBreakpointStep(history, fromStep, breakpoints) {
    if (!history || breakpoints.size === 0) return null;
    const lines = history.executed_lines ?? [];
    for (let step = fromStep + 1; step + 1 < lines.length; step++) {
        if (breakpoints.has(lines[step + 1])) return step;
    }
    return null;
}

// Every recorded stop, in order.
export function breakpointSteps(history, breakpoints) {
    const steps = [];
    for (let step = nextBreakpointStep(history, -1, breakpoints); step !== null;
        step = nextBreakpointStep(history, step, breakpoints)) {
        steps.push(step);
    }
    return steps;
}

// Breakpoints on lines that still exist. Lines are not tracked through
// inserts: an edit that keeps the line count keeps every breakpoint.
export function clampBreakpoints(breakpoints, lineCount) {
    if ([...breakpoints].every((line) => line <= lineCount)) return breakpoints;
    return new Set([...breakpoints].filter((line) => line <= lineCount));
}

export function toggleBreakpoint(breakpoints, line) {
    const next = new Set(breakpoints);
    if (next.has(line)) next.delete(line);
    else next.add(line);
    return next;
}

// A typed step number: { step } when it is in range, else { error }.
export function parseStepInput(text, lastStep) {
    const trimmed = String(text ?? "").trim();
    if (!/^\d+$/.test(trimmed)) return { error: `Enter a step from 0 to ${lastStep}.` };
    const step = Number(trimmed);
    if (step > lastStep) return { error: `The run has ${lastStep} steps. Enter 0 to ${lastStep}.` };
    return { step };
}

// What a step shows: the line that produced it and that line's code.
export function stepSummary(history, source, step) {
    const line = history?.executed_lines?.[step];
    if (line == null) return { line: null, text: "Before the first instruction" };
    const text = (source ?? "").split("\n")[line - 1]?.split("//")[0]
        .replace(/^\s*(?:[\w.$]+:\s*)+/, "").trim();
    return { line, text: text || "(source line unavailable)" };
}
