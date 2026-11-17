import test from 'node:test';
import assert from 'node:assert/strict';
import { blamesProgram, fromClient, fromResponse, fromTransport, showsDetail } from './errors.js';

const structured = {
    error: 'Line 3: This instruction read 8 bytes at 0x0, which is not memory the program owns.',
    error_parts: ['Line 3: ', 'This instruction read ', { kind: 'data', value: '8' }],
    error_info: {
        kind: 'runtime',
        message: 'This instruction read 8 bytes at 0x0, which is not memory the program owns.',
        message_parts: ['This instruction read ', { kind: 'data', value: '8' }],
        line: 3,
        source_line: 'ldr x2, [x0]',
        detail: 'UC_ERR_READ_UNMAPPED',
        suggestion: 'The address is 0, so the program read through a null pointer.',
    },
};

test('a structured error keeps its line, source and advice', () => {
    const error = fromResponse(structured, { status: 400 });
    assert.equal(error.kind, 'runtime');
    assert.equal(error.line, 3);
    assert.equal(error.sourceLine, 'ldr x2, [x0]');
    assert.equal(error.detail, 'UC_ERR_READ_UNMAPPED');
    assert.deepEqual(error.parts, structured.error_info.message_parts);
    assert.ok(blamesProgram(error));
});

test('only a program error is pinned to a line of the source', () => {
    for (const kind of ['assembly', 'unsupported', 'runtime']) {
        assert.ok(blamesProgram(fromResponse({ error_info: { kind, message: 'x' } })));
    }
    for (const kind of ['request', 'internal', 'network']) {
        assert.equal(blamesProgram(fromResponse({ error_info: { kind, message: 'x' } })), false);
    }
});

test('an unknown kind is treated as a simulator problem, not the program', () => {
    const error = fromResponse({ error_info: { kind: 'something-new', message: 'x' } });
    assert.equal(error.kind, 'internal');
    assert.equal(blamesProgram(error), false);
});

test('a payload with only the flat fields still produces a message', () => {
    const error = fromResponse({ error: 'assembly_code must be a string' }, { status: 400 });
    assert.equal(error.kind, 'request');
    assert.equal(error.message, 'assembly_code must be a string');
    assert.equal(error.line, null);
});

test('an empty payload never leaves the message blank', () => {
    assert.equal(fromResponse(null, { status: 503 }).message,
        'The simulator returned HTTP 503.');
    assert.equal(fromResponse(null, { status: 503 }).kind, 'internal');
    assert.equal(fromResponse({}).message, 'The simulation request failed.');
    assert.equal(fromResponse({ error: '   ' }).message, 'The simulation request failed.');
});

test('an HTML error page is reported as a status, not as a parser error', () => {
    const page = '<!doctype html><title>500 Internal Server Error</title>';
    const error = fromTransport(null, { status: 500, body: page });
    assert.equal(error.kind, 'internal');
    assert.match(error.message, /HTTP 500/);
    assert.ok(!error.message.includes('JSON'));
    assert.ok(error.detail.startsWith('<!doctype'));
});

test('a missing endpoint says the backend may be the wrong one', () => {
    const error = fromTransport(null, { status: 404, body: 'Not Found' });
    assert.equal(error.kind, 'request');
    assert.match(error.suggestion, /\/simulate endpoint/);
});

test('a failed fetch names the backend rather than showing "Failed to fetch"', () => {
    const error = fromTransport(new TypeError('Failed to fetch'));
    assert.equal(error.kind, 'network');
    assert.match(error.message, /did not reach the simulator/);
    assert.match(error.suggestion, /port 5001/);
    assert.equal(error.detail, 'Failed to fetch');
});

test('a cancelled request produces no error to show', () => {
    const abort = Object.assign(new Error('aborted'), { name: 'AbortError' });
    assert.equal(fromTransport(abort), null);
    assert.equal(fromClient(abort), null);
});

test('a browser-side consistency failure keeps its own message', () => {
    const error = fromClient(new Error('Continuation changed the recorded stdout.'));
    assert.equal(error.kind, 'internal');
    assert.equal(error.message, 'Continuation changed the recorded stdout.');
    assert.match(error.suggestion, /Load the program again/);
});

test('the raw assembler or CPU code is kept out of a program error', () => {
    // It adds nothing to a sentence that already says what is wrong.
    for (const kind of ['assembly', 'unsupported', 'runtime']) {
        const error = fromResponse({ error_info: { kind, message: 'x', detail: 'KS_ERR_X' } });
        assert.equal(error.detail, 'KS_ERR_X');   // still carried, for tests and logs
        assert.equal(showsDetail(error), false);  // but not shown to the student
    }
    // For a failure of the tool itself it is the only clue there is.
    for (const kind of ['request', 'internal']) {
        assert.equal(showsDetail(fromResponse({ error_info: { kind, message: 'x', detail: 'd' } })), true);
    }
    assert.equal(showsDetail(fromResponse({ error_info: { kind: 'internal', message: 'x' } })), false);
});

test('long text is truncated so one error cannot flood the panel', () => {
    const error = fromResponse({
        error_info: {
            kind: 'assembly', message: 'short',
            source_line: 'x'.repeat(500), suggestion: 'y'.repeat(900),
        },
    });
    assert.equal(error.sourceLine.length, 201);
    assert.equal(error.suggestion.length, 401);
    assert.ok(error.suggestion.endsWith('…'));
});

test('a trace status doubles as an error payload', () => {
    // The visualizer passes history.status straight in after a failed run.
    const status = { state: 'error', kind: 'runtime', ...structured };
    assert.equal(fromResponse(status).line, 3);
});
