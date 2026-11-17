// One shape for every failure the UI shows, whatever its source: a structured
// error from the backend, an HTML error page from a proxy, or a failed fetch.

export const KINDS = {
    assembly: { label: 'Assembly error', blame: 'program' },
    unsupported: { label: 'Not supported', blame: 'program' },
    runtime: { label: 'Runtime error', blame: 'program' },
    request: { label: 'Request problem', blame: 'tool' },
    internal: { label: 'Simulator error', blame: 'tool' },
    network: { label: 'Cannot reach the simulator', blame: 'tool' },
};

const FALLBACK = 'The simulation request failed.';

export function describe(kind) {
    return KINDS[kind] ?? { label: 'Error', blame: 'tool' };
}

// A program error points at the student's source; the others do not.
export function blamesProgram(error) {
    return describe(error?.kind).blame === 'program';
}

// The raw assembler or CPU code is noise next to a sentence that already says
// what is wrong with the program. For a failure of the tool itself it is the
// only clue there is, so it stays.
export function showsDetail(error) {
    return Boolean(error?.detail) && !blamesProgram(error);
}

function trimmed(value, limit = 400) {
    if (typeof value !== 'string') return null;
    const text = value.trim();
    if (!text) return null;
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

/** Normalize whatever a /simulate response carried into one error object. */
export function fromResponse(body, { status } = {}) {
    const info = body?.error_info;
    if (info && typeof info === 'object' && typeof info.message === 'string') {
        return {
            kind: KINDS[info.kind] ? info.kind : 'internal',
            message: info.message,
            parts: Array.isArray(info.message_parts) ? info.message_parts : null,
            line: Number.isInteger(info.line) ? info.line : null,
            sourceLine: trimmed(info.source_line, 200),
            suggestion: trimmed(info.suggestion),
            detail: trimmed(info.detail, 120),
        };
    }
    // An older or partial payload: keep whatever text it has.
    const message = trimmed(body?.error)
        ?? (status ? `The simulator returned HTTP ${status}.` : FALLBACK);
    return {
        kind: status && status >= 500 ? 'internal' : 'request',
        message,
        parts: Array.isArray(body?.error_parts) ? body.error_parts : null,
        line: null,
        sourceLine: null,
        suggestion: null,
        detail: null,
    };
}

/** A failure raised in the browser rather than reported by the backend, such
 *  as a continuation whose recorded prefix no longer matches. */
export function fromClient(error) {
    if (error?.name === 'AbortError') return null;
    return {
        kind: 'internal',
        message: trimmed(error?.message) ?? FALLBACK,
        parts: null,
        line: null,
        sourceLine: null,
        suggestion: 'Load the program again to start a fresh run.',
        detail: null,
    };
}

/** An error for a request that never produced a JSON body. */
export function fromTransport(error, { status, body } = {}) {
    if (error?.name === 'AbortError') return null;
    if (status !== undefined) {
        const detail = trimmed(body, 160);
        return {
            kind: status >= 500 ? 'internal' : 'request',
            message: `The simulator returned HTTP ${status} instead of a result.`,
            parts: null,
            line: null,
            sourceLine: null,
            suggestion: status === 404
                ? 'The /simulate endpoint was not found. Check that the backend is the one this page proxies to.'
                : 'Check the backend terminal for the full error.',
            // Keep a short excerpt so an HTML error page is still diagnosable.
            detail: detail && !detail.startsWith('{') ? detail : null,
        };
    }
    return {
        kind: 'network',
        message: 'The request did not reach the simulator backend.',
        parts: null,
        line: null,
        sourceLine: null,
        suggestion: 'Start it with "python3 -m flask --app app run --port 5001" in the backend '
            + 'directory, then load the program again.',
        detail: trimmed(error?.message, 120),
    };
}
