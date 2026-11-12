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
