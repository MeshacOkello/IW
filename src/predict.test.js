import test from 'node:test';
import assert from 'node:assert/strict';
import {
    checkPredictions, decodeInstruction, emptyScore, formatValue, parseNumberInput,
    predictionFields, recordCheck,
} from './predict.js';

const STACK_TOP = 0x9000;
const N = 1 << 31, Z = 1 << 30, C = 1 << 29, V = 1 << 28;

function registers(overrides = {}) {
    const values = Array(34).fill(0);
    values[31] = STACK_TOP;
    values[32] = 0x1000;
    for (const [name, value] of Object.entries(overrides)) {
        const index = name === 'sp' ? 31 : name === 'pc' ? 32 : name === 'nzcv' ? 33 : Number(name.slice(1));
        values[index] = value;
    }
    return values;
}

// A two-step trace: the snapshot before one instruction and the one after.
// `stack` lists the written 8-byte cells after it, as { address: value }.
function trace({ before = {}, after = {}, writes = [], stack = {} }) {
    const first = registers(before);
    const second = registers({ pc: first[32] + 4, ...before, ...after });
    const cells = Object.entries(stack).map(([address, value]) => ({ address: Number(address), size: 8, value }));
    const exact = Object.fromEntries(
        Object.entries(stack).filter(([, value]) => typeof value === 'string').map(([a, v]) => [a, v]));
    return {
        register_states: [first, second],
        exact_values: [null, Object.keys(exact).length ? { registers: {}, stack: exact } : null],
        stack_states: [[], cells],
        frame_states: [[{ stack_start: first[31], stack_end: STACK_TOP }],
                       [{ stack_start: second[31], stack_end: STACK_TOP }]],
        memory_accesses: [[], writes.map(([address, size]) => ({ kind: 'write', address, size }))],
        heap_states: [[], []],
        heap_allocations: { versions: [], chunks: [] },
        sections: { layout: [], versions: [] },
        section_states: [{}, {}],
    };
}

const ids = (fields) => fields.map((field) => field.id);
const check = (fields, answers) => checkPredictions(fields, answers);

test('mov, add, sub and mul ask only for their destination register', () => {
    const cases = [
        ['mov x1, #20', { x1: 0 }, { x1: 20 }, 'reg:1', '20'],
        ['add x3, x1, x2', { x1: 20, x2: 5 }, { x3: 25 }, 'reg:3', '0x19'],
        ['sub x4, x1, x2', { x1: 20, x2: 5 }, { x4: 15 }, 'reg:4', '15'],
        ['mul x5, x3, x2', { x3: 25, x2: 5 }, { x5: 125 }, 'reg:5', '125'],
    ];
    for (const [line, before, after, id, answer] of cases) {
        const { fields } = predictionFields(trace({ before, after }), 0, line);
        assert.deepEqual(ids(fields), [id], line);
        assert.equal(check(fields, { [id]: answer }).correct, 1, line);
        assert.equal(check(fields, { [id]: '7' }).results[id].status, 'wrong', line);
    }
});

test('a destination is asked about even when its value does not change', () => {
    const { fields } = predictionFields(trace({ before: { x1: 5 } }), 0, 'mov x1, 5');
    assert.deepEqual(ids(fields), ['reg:1']);
    // An untouched field keeps the current value as its answer.
    assert.equal(check(fields, {}).results['reg:1'].status, 'correct');
});

test('the source line can carry a label and a comment', () => {
    const info = decodeInstruction('loop:   add x0, x0, x3   // sum += x3');
    assert.equal(info.mnemonic, 'add');
    assert.deepEqual(info.destinations.map((d) => d.index), [0]);
});

test('cmp always asks for all four flags and scores each one', () => {
    const cases = [
        ['N', { x1: 1, x2: 2 }, N],          // 1 - 2 is negative, borrow
        ['Z', { x1: 4, x2: 4 }, Z | C],      // equal, no borrow
        ['C', { x1: 3, x2: 1 }, C],          // positive, no borrow
        ['V', { x1: 0x7fffffffffffffffn, x2: 0xffffffffffffffffn }, N | V],
    ];
    for (const [flag, before, nzcv] of cases) {
        const history = trace({ before, after: { nzcv } });
        const { fields } = predictionFields(history, 0, 'cmp x1, x2');
        assert.deepEqual(ids(fields), ['flag:N', 'flag:Z', 'flag:C', 'flag:V'], flag);
        const right = Object.fromEntries(fields.map((f) => [f.id, String(f.expected)]));
        assert.equal(check(fields, right).correct, 4, flag);
        assert.equal(fields.find((f) => f.flag === flag).expected, 1n, flag);
        const wrong = { ...right, [`flag:${flag}`]: '0' };
        assert.equal(check(fields, wrong).results[`flag:${flag}`].status, 'wrong', flag);
    }
});

test('flag fields appear for cmp even when the flags stay the same', () => {
    const history = trace({ before: { nzcv: Z | C }, after: { nzcv: Z | C } });
    const { fields } = predictionFields(history, 0, 'cmp x0, x0');
    assert.equal(fields.length, 4);
    assert.equal(check(fields, {}).correct, 4);
});

test('str with an offset asks for the address and the stored value, not the base', () => {
    const history = trace({
        before: { sp: 0x8ff0, x0: 4 },
        writes: [[0x8ff8, 8]],
        stack: { 0x8ff8: 4 },
    });
    const { fields } = predictionFields(history, 0, 'str x0, [sp, 8]');
    assert.deepEqual(ids(fields), ['mem:0:address', 'mem:0:value']);
    assert.equal(fields[0].region, 'stack');
    const result = check(fields, { 'mem:0:address': '0x8ff8', 'mem:0:value': '4' });
    assert.equal(result.correct, 2);
    assert.equal(check(fields, { 'mem:0:address': '0x8ff0' }).results['mem:0:address'].status, 'wrong');
    assert.equal(check(fields, {}).results['mem:0:value'].status, 'missing');
});

test('ldr with an offset asks only for the loaded register', () => {
    const history = trace({ before: { sp: 0x8ff0 }, after: { x1: 4 } });
    const { fields } = predictionFields(history, 0, 'ldr x1, [sp, LN]');
    assert.deepEqual(ids(fields), ['reg:1']);
});

test('pre-index stores ask for the base register written back', () => {
    const history = trace({
        before: { x30: 0x1040 },
        after: { sp: 0x8ff0 },
        writes: [[0x8ff0, 8]],
        stack: { 0x8ff0: 0x1040 },
    });
    const { fields } = predictionFields(history, 0, 'str x30, [sp, -16]!');
    assert.deepEqual(ids(fields), ['reg:31', 'mem:0:address', 'mem:0:value']);
    const answers = { 'reg:31': String(0x8ff0), 'mem:0:address': '0x8ff0', 'mem:0:value': '0x1040' };
    assert.equal(check(fields, answers).correct, 3);
});

test('post-index loads ask for the loaded register and the advanced base', () => {
    const history = trace({ before: { x1: 0x2000 }, after: { x1: 0x2008, x3: 3 } });
    const { fields } = predictionFields(history, 0, 'ldr x3, [x1], 8');
    assert.deepEqual(ids(fields), ['reg:1', 'reg:3']);
    assert.equal(check(fields, { 'reg:1': '0x2008', 'reg:3': '3' }).correct, 2);
    // Forgetting the writeback leaves x1 unchanged, which is wrong.
    assert.equal(check(fields, { 'reg:3': '3' }).results['reg:1'].status, 'wrong');
});

test('stp on sp with pre-index asks for sp and both stored slots', () => {
    const history = trace({
        before: { x29: 0x8ff0, x30: 0x1010 },
        after: { sp: 0x8fe0 },
        writes: [[0x8fe0, 8], [0x8fe8, 8]],
        stack: { 0x8fe0: 0x8ff0, 0x8fe8: 0x1010 },
    });
    const { fields } = predictionFields(history, 0, 'stp x29, x30, [sp, -16]!');
    assert.deepEqual(ids(fields), ['reg:31', 'mem:0:address', 'mem:0:value', 'mem:1:address', 'mem:1:value']);
    assert.deepEqual(fields.slice(1).map((f) => f.expected), [0x8fe0n, 0x8ff0n, 0x8fe8n, 0x1010n]);
    const answers = {
        'reg:31': '0x8fe0',
        'mem:0:address': '0x8fe0', 'mem:0:value': '0x8ff0',
        'mem:1:address': '0x8fe8', 'mem:1:value': '0x1010',
    };
    assert.equal(check(fields, answers).correct, 5);
});

test('stp reported as one 16-byte write still splits into two slots', () => {
    const history = trace({
        before: { sp: 0x8ff0, x0: 1, x1: 2 },
        writes: [[0x8fe0, 16]],
        stack: { 0x8fe0: 1, 0x8fe8: 2 },
    });
    const { fields } = predictionFields(history, 0, 'stp x0, x1, [sp, -16]');
    assert.deepEqual(fields.filter((f) => f.kind === 'value').map((f) => f.expected), [1n, 2n]);
});

test('ldp on sp with post-index asks for both registers and sp', () => {
    const history = trace({
        before: { sp: 0x8fe0 },
        after: { sp: 0x8ff0, x29: 0x8ff0, x30: 0x1010 },
    });
    const { fields } = predictionFields(history, 0, 'ldp x29, x30, [sp], 16');
    assert.deepEqual(ids(fields), ['reg:29', 'reg:30', 'reg:31']);
});

test('b.cond asks taken or not taken, judged by where pc went', () => {
    const taken = trace({ after: { pc: 0x1040 } });
    const { fields } = predictionFields(taken, 0, 'b.gt factRecurse');
    assert.deepEqual(ids(fields), ['branch']);
    assert.equal(fields[0].expected, 'taken');
    assert.equal(check(fields, { branch: 'taken' }).correct, 1);
    assert.equal(check(fields, { branch: 'not-taken' }).correct, 0);
    assert.equal(check(fields, {}).results.branch.status, 'missing');

    const fallsThrough = trace({});
    const notTaken = predictionFields(fallsThrough, 0, 'bgt factRecurse').fields;
    assert.equal(notTaken[0].expected, 'not-taken');
    assert.equal(check(notTaken, { branch: 'not-taken' }).correct, 1);
});

test('bl asks for x30 and the branch; a library call leaves x0 unscored', () => {
    const call = trace({ before: { x0: 4 }, after: { x30: 0x1004, pc: 0x1100 } });
    assert.deepEqual(ids(predictionFields(call, 0, 'bl fact').fields), ['reg:30', 'branch']);

    const printf = trace({ after: { x0: 12, x30: 0x1004 } });
    const result = predictionFields(printf, 0, 'bl printf');
    assert.equal(result.info.libraryCall, 'printf');
    assert.deepEqual(ids(result.fields), ['reg:30', 'branch']);
    assert.equal(result.fields[1].expected, 'taken');
});

test('numbers are read as hex with 0x and as decimal otherwise, either sign', () => {
    assert.equal(parseNumberInput('42'), 42n);
    assert.equal(parseNumberInput('-42'), -42n);
    assert.equal(parseNumberInput('0x2A'), 42n);
    assert.equal(parseNumberInput('-0x2a'), -42n);
    assert.equal(parseNumberInput(' 0xffffffffffffffff '), (1n << 64n) - 1n);
    assert.equal(parseNumberInput('2a'), null);
    assert.equal(parseNumberInput(''), null);
    assert.equal(parseNumberInput('0x10000000000000000'), null);
});

test('negative answers match 64-bit registers with wraparound', () => {
    const history = trace({ after: { x0: 0xffffffffffffffffn } });
    const { fields } = predictionFields(history, 0, 'mov x0, -1');
    for (const answer of ['-1', '-0x1', '0xFFFFFFFFFFFFFFFF', '18446744073709551615']) {
        assert.equal(check(fields, { 'reg:0': answer }).correct, 1, answer);
    }
    assert.equal(check(fields, { 'reg:0': '0xFFFFFFFF' }).correct, 0);
});

test('a w destination accepts its 32-bit value, signed or not', () => {
    const history = trace({ after: { x0: 0xffffffff } });
    const { fields } = predictionFields(history, 0, 'mov w0, -1');
    assert.equal(fields[0].bits, 32);
    for (const answer of ['-1', '0xFFFFFFFF', '4294967295']) {
        assert.equal(check(fields, { 'reg:0': answer }).correct, 1, answer);
    }
    // The top half of x0 is cleared, so the 64-bit -1 is wrong.
    assert.equal(check(fields, { 'reg:0': '0xFFFFFFFFFFFFFFFF' }).correct, 0);
});

test('strb and strh compare only the bytes they store', () => {
    const byte = trace({
        before: { sp: 0x8ff0, x2: 0xffffffffffffffffn },
        writes: [[0x8ff0, 1]],
        stack: { 0x8ff0: 0xff },
    });
    const strb = predictionFields(byte, 0, 'strb w2, [sp]').fields;
    assert.equal(strb[1].bits, 8);
    assert.equal(strb[1].expected, 0xffn);
    for (const answer of ['-1', '0xFF', '255']) {
        assert.equal(check(strb, { 'mem:0:address': '0x8ff0', 'mem:0:value': answer }).correct, 2, answer);
    }

    const half = trace({
        before: { sp: 0x8ff0, x2: 0x12345 },
        writes: [[0x8ff0, 2]],
        stack: { 0x8ff0: 0x2345 },
    });
    const strh = predictionFields(half, 0, 'strh w2, [sp]').fields;
    assert.equal(strh[1].expected, 0x2345n);
    assert.equal(check(strh, { 'mem:0:address': '0x8ff0', 'mem:0:value': '0x12345' }).correct, 2);
});

test('a store outside every displayed region falls back to the source register', () => {
    const history = trace({ before: { sp: 0x8ff0, x5: 9 }, writes: [[0x8fe8, 8]] });
    const { fields } = predictionFields(history, 0, 'str x5, [sp, -8]');
    assert.equal(fields[1].expected, 9n);
    assert.equal(fields[1].region, 'memory');
});

test('exact stack values beyond 2^53 are read from the exact table', () => {
    const big = '18446744073709551615';
    const history = trace({ before: { sp: 0x8ff0 }, writes: [[0x8ff0, 8]], stack: { 0x8ff0: big } });
    history.stack_states[1][0].value = Number(big);
    const { fields } = predictionFields(history, 0, 'str x9, [sp]');
    assert.equal(fields[1].expected, BigInt(big));
});

test('a step is scored once, however often it is predicted again', () => {
    const { fields } = predictionFields(trace({ after: { x1: 20 } }), 0, 'mov x1, 20');
    const wrong = check(fields, { 'reg:1': '2' });
    const first = recordCheck(emptyScore(), { step: 0, line: 1, instruction: 'mov x1, 20', fields, check: wrong });
    assert.equal(first.counted, true);
    assert.deepEqual([first.score.correct, first.score.total], [0, 1]);
    assert.equal(first.score.missed[0].wrong[0].field.label, 'x1');

    const again = recordCheck(first.score, {
        step: 0, line: 1, instruction: 'mov x1, 20', fields, check: check(fields, { 'reg:1': '20' }),
    });
    assert.equal(again.counted, false);
    assert.deepEqual([again.score.correct, again.score.total], [0, 1]);
});

test('values are shown unsigned, with the signed reading in decimal', () => {
    assert.equal(formatValue(-1n, 64, 'hex'), '0xFFFFFFFFFFFFFFFF');
    assert.equal(formatValue(-1n, 64, 'dec'), '18446744073709551615 (-1)');
    assert.equal(formatValue(0xffn, 8, 'dec'), '255 (-1)');
    assert.equal(formatValue(25n, 64, 'dec'), '25');
});
