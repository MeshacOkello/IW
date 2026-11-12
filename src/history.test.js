import test from 'node:test';
import assert from 'node:assert/strict';
import { extendHistory, stdoutAt, inputPrompt } from './history.js';

function trace(steps, chunks = []) {
    return {
        register_states: steps.map((value) => [value]),
        stdout_states: steps,
        stdout: { chunks },
        heap_allocations: { versions: [], chunks: [] },
        sections: { layout: [], versions: [] },
        run_settings: { execution_limit: 10000 },
    };
}

test('continuation preserves the existing snapshot objects and rejects a changed prefix', () => {
    const before = trace([0, 1], ['41']);
    const after = trace([0, 1, 2], ['41', '42']);
    const extended = extendHistory(before, after);
    assert.equal(extended.register_states[0], before.register_states[0]);
    assert.equal(stdoutAt(extended, 1), 'A');
    assert.equal(stdoutAt(extended, 2), 'AB');
    assert.throws(() => extendHistory(before, trace([0, 2], ['41'])), /recorded/);
    assert.throws(() => extendHistory(before, trace([0, 1, 2], ['42', '41'])), /stdout/);
    assert.deepEqual(before, trace([0, 1], ['41']));
});

test('UTF-8 stdout is decoded cumulatively and retains spaces and incomplete lines', () => {
    const history = trace([0, 1, 2, 3], ['c3', 'a9', '202074657874']);
    assert.equal(stdoutAt(history, 0), '');
    assert.equal(stdoutAt(history, 1), '�');
    assert.equal(stdoutAt(history, 2), 'é');
    assert.equal(stdoutAt(history, 3), 'é  text');
});

test('modal title uses only the final prompt-like line in the current input window', () => {
    const chunk = (text) => Array.from(new TextEncoder().encode(text), byte => byte.toString(16).padStart(2, '0')).join('');
    const history = trace([0, 1, 2], [chunk('Earlier output\n'), chunk('Enter your name: ')]);
    assert.equal(inputPrompt(history, {stdout_start: 0}), 'Enter your name:');
    assert.equal(inputPrompt(history, {stdout_start: 2}), 'Input');
    assert.equal(inputPrompt(trace([0, 1], [chunk('Earlier output\n')]), {stdout_start: 0}), 'Input');
    assert.equal(inputPrompt(trace([0, 1], [chunk('Choose an option?\n')]), {stdout_start: 0}), 'Choose an option?');
    assert.equal(inputPrompt(trace([0], []), {stdout_start: 0}), 'Input');
});
