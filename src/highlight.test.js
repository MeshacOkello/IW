import test from 'node:test';
import assert from 'node:assert/strict';
import { highlightLine } from './highlight.js';

const kinds = (line) => highlightLine(line)
    .filter((token) => token.kind !== 'plain')
    .map((token) => `${token.kind}:${token.text}`);

test('the spans always join back into the original line', () => {
    for (const line of [
        '    mov x1, #20      // First value',
        'main:',
        '.text',
        '',
        '   ',
        'loop: add x3, x1, x2',
        '.rodata',
        'msg: .asciz "hello, world\\n"',
        'ldr x0, [sp, #-16]!',
        'adrp x0, label',
        'add x0, x0, :lo12:label',
        'stp x29, x30, [sp, #-16]!',
        "mov x0, #'a'",
        'b.eq done',
        'ldr x0, =0x1234',
        '\t\tsub\tx4,\tx1,\tx2',
        'weird ~!@%^&*()',
    ]) {
        assert.equal(highlightLine(line).map((token) => token.text).join(''), line, line);
    }
});

test('each kind of token is recognised', () => {
    assert.deepEqual(kinds('.text'), ['directive:.text']);
    assert.deepEqual(kinds('main:'), ['label:main:']);
    assert.deepEqual(kinds('    mov x1, #20      // First value'),
        ['mnemonic:mov', 'register:x1', 'immediate:#20', 'comment:// First value']);
    assert.deepEqual(kinds('add x3, x1, x2'),
        ['mnemonic:add', 'register:x3', 'register:x1', 'register:x2']);
    assert.deepEqual(kinds('msg: .asciz "hi"'),
        ['label:msg:', 'directive:.asciz', 'string:"hi"']);
});

test('a label defined and a label referred to are told apart', () => {
    // The first word names the operation; a bare word after it is a target.
    assert.deepEqual(kinds('loop: b loop'), ['label:loop:', 'mnemonic:b', 'name:loop']);
    assert.deepEqual(kinds('bl printf'), ['mnemonic:bl', 'name:printf']);
});

test('registers are matched only as whole operands', () => {
    assert.deepEqual(kinds('mov x30, sp'), ['mnemonic:mov', 'register:x30', 'register:sp']);
    assert.deepEqual(kinds('mov xzr, wzr'), ['mnemonic:mov', 'register:xzr', 'register:wzr']);
    // x32 is not a register, and a label that merely starts with one is a name.
    assert.deepEqual(kinds('mov x32, #1'), ['mnemonic:mov', 'name:x32', 'immediate:#1']);
    assert.deepEqual(kinds('b x1_loop'), ['mnemonic:b', 'name:x1_loop']);
});

test('a comment runs to the end of the line, whatever it contains', () => {
    assert.deepEqual(kinds('nop // mov x1, #20 "quoted" .text'),
        ['mnemonic:nop', 'comment:// mov x1, #20 "quoted" .text']);
    assert.deepEqual(kinds('// a whole-line comment'), ['comment:// a whole-line comment']);
});

test('an unterminated string does not swallow the scan', () => {
    assert.deepEqual(kinds('.asciz "oops'), ['directive:.asciz', 'string:"oops']);
    assert.equal(highlightLine('.asciz "oops').map((token) => token.text).join(''), '.asciz "oops');
});

test('memory operands keep their brackets as plain text', () => {
    assert.deepEqual(kinds('ldr x0, [sp, #-16]!'),
        ['mnemonic:ldr', 'register:x0', 'register:sp', 'immediate:#-16']);
});
