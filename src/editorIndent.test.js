import test from 'node:test';
import assert from 'node:assert/strict';
import { INDENT, indentEdit } from './editorIndent.js';

// Write the case as text with | for the caret, or [ ] around a selection.
function at(marked) {
    const start = marked.indexOf('[');
    if (start !== -1) {
        const end = marked.indexOf(']') - 1;
        return { value: marked.replace(/[[\]]/g, ''), selectionStart: start, selectionEnd: end };
    }
    const caret = marked.indexOf('|');
    return { value: marked.replace('|', ''), selectionStart: caret, selectionEnd: caret };
}

function apply(marked, { outdent = false } = {}) {
    const state = at(marked);
    const edit = indentEdit({ ...state, outdent });
    if (!edit) return null;
    const value = state.value.slice(0, edit.start) + edit.text + state.value.slice(edit.end);
    const from = edit.caret ?? edit.selectionStart;
    const to = edit.caret ?? edit.selectionEnd;
    return from === to
        ? value.slice(0, from) + '|' + value.slice(from)
        : value.slice(0, from) + '[' + value.slice(from, to) + ']' + value.slice(to);
}

test('Tab indents to the next tab stop, not by a fixed amount', () => {
    assert.equal(INDENT.length, 4);
    assert.equal(apply('|mov x0, #1'), '    |mov x0, #1');
    assert.equal(apply('m|ov x0, #1'), 'm   |ov x0, #1');
    assert.equal(apply('mo|v x0, #1'), 'mo  |v x0, #1');
    assert.equal(apply('mov| x0, #1'), 'mov | x0, #1');   // one space, to column 4
    assert.equal(apply('mov |x0, #1'), 'mov     |x0, #1');
});

test('the tab stop is counted from the start of the line, not the file', () => {
    assert.equal(apply('nop\nm|ov x0, #1'), 'nop\nm   |ov x0, #1');
});

test('Tab replaces a selection inside one line', () => {
    assert.equal(apply('mov [x0], #1'), 'mov     |, #1');
});

test('Tab shifts every line a selection touches', () => {
    assert.equal(apply('[mov x0, #1\nmov x1], #2'),
        '[    mov x0, #1\n    mov x1], #2');
});

test('a selection ending just after a newline does not reach the line below', () => {
    assert.equal(apply('[mov x0, #1\n]mov x1, #2'),
        '[    mov x0, #1\n]mov x1, #2');
});

test('Shift+Tab removes one level of indentation', () => {
    assert.equal(apply('        mo|v x0, #1', { outdent: true }), '    mo|v x0, #1');
    assert.equal(apply('  mo|v x0, #1', { outdent: true }), 'mo|v x0, #1');
    assert.equal(apply('\tmo|v x0, #1', { outdent: true }), 'mo|v x0, #1');
});

test('a block selected from the margin stays selected, so Tab can repeat', () => {
    const once = apply('[mov x0, #1\nmov x1], #2');
    assert.equal(once, '[    mov x0, #1\n    mov x1], #2');
    assert.equal(apply(once), '[        mov x0, #1\n        mov x1], #2');
});

test('a selection starting mid-line moves with its text', () => {
    assert.equal(apply('mov [x0, #1\nmov x1], #2'),
        '    mov [x0, #1\n    mov x1], #2');
});

test('Shift+Tab outdents every line a selection touches, and never past the margin', () => {
    assert.equal(apply('[    mov x0, #1\n        mov x1], #2', { outdent: true }),
        '[mov x0, #1\n    mov x1], #2');
    // A line already at the margin is left alone rather than eating its text.
    assert.equal(apply('[mov x0, #1\n    mov x1], #2', { outdent: true }),
        '[mov x0, #1\nmov x1], #2');
});

test('Shift+Tab on text with no indentation does nothing at all', () => {
    assert.equal(indentEdit({ ...at('mo|v x0, #1'), outdent: true }), null);
    assert.equal(indentEdit({ ...at('[mov x0, #1\nmov x1], #2'), outdent: true }), null);
});
