import test from 'node:test';
import assert from 'node:assert/strict';
import {
    breakpointSteps, clampBreakpoints, isBreakpointStop, nextBreakpointStep,
    parseStepInput, stepSummary, toggleBreakpoint,
} from './timeline.js';

// executed_lines as the backend records it: step 0 has run nothing.
const trace = (...lines) => ({ executed_lines: [null, ...lines] });

// A loop: lines 1-2 set up, 3-5 repeat three times, 6 returns.
const loop = trace(1, 2, 3, 4, 5, 3, 4, 5, 3, 4, 5, 6);

test('no breakpoints never stops', () => {
    assert.equal(nextBreakpointStep(loop, 0, new Set()), null);
    assert.equal(isBreakpointStop(loop, 2, new Set()), false);
    assert.deepEqual(breakpointSteps(loop, new Set()), []);
    assert.equal(nextBreakpointStep(null, 0, new Set([3])), null);
});

test('a stop leaves the breakpoint line about to run', () => {
    // Line 3 first runs at step 3, so the stop is step 2.
    assert.equal(nextBreakpointStep(loop, 0, new Set([3])), 2);
    assert.equal(isBreakpointStop(loop, 2, new Set([3])), true);
    assert.equal(loop.executed_lines[2 + 1], 3);
});

test('the current step is skipped, so continuing moves past a breakpoint', () => {
    const breakpoints = new Set([3]);
    assert.equal(nextBreakpointStep(loop, 2, breakpoints), 5);
    // A breakpoint on the very first instruction stops at step 0 only when
    // searching from before it.
    assert.equal(nextBreakpointStep(trace(3, 4), -1, breakpoints), 0);
    assert.equal(nextBreakpointStep(trace(3, 4), 0, breakpoints), null);
});

test('a breakpoint inside a loop is hit again on every later iteration', () => {
    const breakpoints = new Set([4]);
    assert.deepEqual(breakpointSteps(loop, breakpoints), [3, 6, 9]);
    assert.equal(nextBreakpointStep(loop, 3, breakpoints), 6);
    assert.equal(nextBreakpointStep(loop, 6, breakpoints), 9);
    assert.equal(nextBreakpointStep(loop, 9, breakpoints), null);
    // Two breakpoints interleave in execution order.
    assert.deepEqual(breakpointSteps(loop, new Set([4, 6])), [3, 6, 9, 11]);
});

test('a breakpoint that is never reached never stops', () => {
    assert.equal(nextBreakpointStep(loop, 0, new Set([42])), null);
    assert.deepEqual(breakpointSteps(loop, new Set([42])), []);
});

test('history that grows after stdin input exposes stops in the new steps', () => {
    // Waiting at the last recorded step: the call that reads input (line 5)
    // has not been recorded yet, nor anything after it.
    const waiting = trace(1, 2, 3, 4);
    const breakpoints = new Set([7]);
    assert.equal(nextBreakpointStep(waiting, 4, breakpoints), null);

    const extended = trace(1, 2, 3, 4, 5, 6, 7, 8);
    assert.equal(nextBreakpointStep(extended, 4, breakpoints), 6);
    assert.equal(isBreakpointStop(extended, 6, breakpoints), true);
    // The last recorded step has no next instruction, so it is never a stop.
    assert.equal(isBreakpointStop(extended, 8, new Set([8])), false);
});

test('edits keep breakpoints unless their line is gone', () => {
    const breakpoints = new Set([2, 5, 9]);
    assert.equal(clampBreakpoints(breakpoints, 9), breakpoints);
    assert.equal(clampBreakpoints(breakpoints, 12), breakpoints);
    assert.deepEqual([...clampBreakpoints(breakpoints, 6)], [2, 5]);
    assert.deepEqual([...clampBreakpoints(breakpoints, 1)], []);
});

test('toggling adds and removes a line without touching the original', () => {
    const breakpoints = new Set([2]);
    assert.deepEqual([...toggleBreakpoint(breakpoints, 4)].sort(), [2, 4]);
    assert.deepEqual([...toggleBreakpoint(breakpoints, 2)], []);
    assert.deepEqual([...breakpoints], [2]);
});

test('a typed step must be a whole number in range', () => {
    assert.deepEqual(parseStepInput('7', 12), { step: 7 });
    assert.deepEqual(parseStepInput(' 0 ', 12), { step: 0 });
    assert.match(parseStepInput('13', 12).error, /0 to 12/);
    assert.match(parseStepInput('-1', 12).error, /0 to 12/);
    assert.match(parseStepInput('2.5', 12).error, /0 to 12/);
    assert.match(parseStepInput('', 12).error, /0 to 12/);
});

test('a step summary names the line that produced it', () => {
    const source = 'main:\n  mov x1, 20 // twenty\nloop: add x0, x0, x1';
    const history = trace(2, 3);
    assert.deepEqual(stepSummary(history, source, 0), { line: null, text: 'Before the first instruction' });
    assert.deepEqual(stepSummary(history, source, 1), { line: 2, text: 'mov x1, 20' });
    assert.deepEqual(stepSummary(history, source, 2), { line: 3, text: 'add x0, x0, x1' });
});
