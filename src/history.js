function requireSamePrefix(previous, next, label) {
    if (!Array.isArray(next) || next.length < previous.length ||
        JSON.stringify(previous) !== JSON.stringify(next.slice(0, previous.length))) {
        throw new Error(`Continuation changed the recorded ${label}. Reload the program.`);
    }
    return [...previous, ...next.slice(previous.length)];
}

export function extendHistory(previous, next) {
    const merged = { ...next };
    for (const [key, value] of Object.entries(previous)) {
        if (Array.isArray(value)) merged[key] = requireSamePrefix(value, next[key], key);
    }
    if (JSON.stringify(previous.run_settings) !== JSON.stringify(next.run_settings) ||
        JSON.stringify(previous.sections.layout) !== JSON.stringify(next.sections.layout)) {
        throw new Error('Continuation changed the run settings or section layout. Reload the program.');
    }
    merged.heap_allocations = {
        chunks: requireSamePrefix(previous.heap_allocations.chunks, next.heap_allocations.chunks, 'heap bytes'),
        versions: requireSamePrefix(previous.heap_allocations.versions, next.heap_allocations.versions, 'heap versions'),
    };
    merged.sections = {
        ...next.sections,
        versions: requireSamePrefix(previous.sections.versions, next.sections.versions, 'section versions'),
    };
    merged.stdout = {
        ...next.stdout,
        chunks: requireSamePrefix(previous.stdout.chunks, next.stdout.chunks, 'stdout'),
    };
    return merged;
}

function decodeChunks(chunks) {
    const hex = chunks.join('');
    const bytes = Uint8Array.from(hex.match(/../g) ?? [], (byte) => parseInt(byte, 16));
    return new TextDecoder('utf-8').decode(bytes);
}

export function stdoutAt(history, step) {
    const count = history?.stdout_states?.[step] ?? 0;
    return decodeChunks(history?.stdout?.chunks.slice(0, count) ?? []);
}

export function inputPrompt(history, pending) {
    const start = pending?.stdout_start ?? 0;
    const output = decodeChunks(history?.stdout?.chunks.slice(start) ?? []);
    const line = output.trimEnd().split(/\r?\n/).at(-1)?.trim() ?? '';
    // Limit prompt detection to the final line with a conventional prompt ending.
    return /[:?>]$/.test(line) ? line : 'Input';
}

// Cache one immutable activity timeline per trace, rather than rescanning its
// prefix on every playback step. Continuation produces a new trace object.
const registerActivity = new WeakMap();

export function touchedRegistersAt(history, step) {
    if (!history) return new Set();
    let timeline = registerActivity.get(history);
    if (!timeline) {
        let touched = new Set();
        timeline = [touched];
        for (let index = 1; index < history.register_states.length; index++) {
            const written = new Set(history.register_writes?.[index] ?? []);
            // Numerical changes also establish writes in older traces.
            for (let register = 0; register < 31; register++) {
                if (history.register_states[index][register] !== history.register_states[index - 1][register]) {
                    written.add(register);
                }
            }
            if ([...written].some(register => !touched.has(register))) {
                touched = new Set([...touched, ...written]);
            }
            timeline.push(touched);
        }
        registerActivity.set(history, timeline);
    }
    return timeline[step];
}
