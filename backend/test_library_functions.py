"""isspace and printf field widths, as the COS 217 word-count program uses them."""
import unittest

from app import app
from library_io import LibraryError, isspace, printf_parts


def output(trace, step=-1):
    count = trace['stdout_states'][step]
    return bytes.fromhex(''.join(trace['stdout']['chunks'][:count])).decode('utf-8', errors='replace')


# The COS 217 word-count program: counts lines, words and characters on
# stdin and prints them with "%7ld %7ld %7ld\n".
WORD_COUNT = '''        .section .rodata
printfFormatStr:
        .string "%7ld %7ld %7ld\\n"

        .section .data
lLineCount:     .quad 0
lWordCount:     .quad 0
lCharCount:     .quad 0
iInWord:        .word 0

        .section .bss
iChar:  .skip 4

        .section .text
        .equ FALSE, 0
        .equ TRUE, 1
        .equ EOF, -1
        .equ MAIN_STACK_BYTECOUNT, 16

        .global main
main:
        sub     sp, sp, MAIN_STACK_BYTECOUNT
        str     x30, [sp]
readLoop:
        bl      getchar
        adr     x1, iChar
        str     w0, [x1]
        cmp     w0, EOF
        beq     readLoopEnd
        adr     x1, lCharCount
        ldr     x2, [x1]
        add     x2, x2, 1
        str     x2, [x1]
        adr     x1, iChar
        ldr     w0, [x1]
        bl      isspace
        cmp     w0, FALSE
        beq     notSpace
        adr     x1, iInWord
        ldr     w2, [x1]
        cmp     w2, FALSE
        beq     checkNewline
        adr     x1, lWordCount
        ldr     x2, [x1]
        add     x2, x2, 1
        str     x2, [x1]
        adr     x1, iInWord
        mov     w2, FALSE
        str     w2, [x1]
        b       checkNewline
notSpace:
        adr     x1, iInWord
        mov     w2, TRUE
        str     w2, [x1]
checkNewline:
        adr     x1, iChar
        ldr     w2, [x1]
        cmp     w2, 10
        bne     readLoop
        adr     x1, lLineCount
        ldr     x2, [x1]
        add     x2, x2, 1
        str     x2, [x1]
        b       readLoop
readLoopEnd:
        adr     x1, iInWord
        ldr     w2, [x1]
        cmp     w2, FALSE
        beq     printCounts
        adr     x1, lWordCount
        ldr     x2, [x1]
        add     x2, x2, 1
        str     x2, [x1]
printCounts:
        adr     x0, printfFormatStr
        adr     x1, lLineCount
        ldr     x1, [x1]
        adr     x2, lWordCount
        ldr     x2, [x2]
        adr     x3, lCharCount
        ldr     x3, [x3]
        bl      printf
        mov     w0, 0
        ldr     x30, [sp]
        add     sp, sp, MAIN_STACK_BYTECOUNT
        ret
'''


class IsspaceTests(unittest.TestCase):
    def test_c_locale_whitespace_is_true_and_everything_else_false(self):
        for value in b' \t\n\v\f\r':
            with self.subTest(value=value):
                self.assertEqual(isspace(value), 1)
        for value in [0, ord('a'), ord('Z'), ord('0'), 0x1c, 0x85, 0xa0, 255]:
            with self.subTest(value=value):
                self.assertEqual(isspace(value), 0)

    def test_eof_is_false_and_only_w0_is_read(self):
        self.assertEqual(isspace(0xffffffff), 0)            # EOF as getchar returns it
        self.assertEqual(isspace(0xffffffffffffffff), 0)    # sign-extended EOF in x0
        self.assertEqual(isspace((7 << 32) | 32), 1)        # junk above w0 is ignored

    def test_values_outside_eof_and_unsigned_char_are_errors(self):
        for value in [256, 0xfffffffe, 0x80000000, 0xffffff80]:
            with self.subTest(value=value), self.assertRaises(LibraryError) as raised:
                isspace(value)
            self.assertEqual(raised.exception.kind, 'runtime')
            self.assertTrue(str(raised.exception).startswith('isspace requires'))


class PrintfWidthParsingTests(unittest.TestCase):
    def test_widths_attach_to_their_conversion(self):
        self.assertEqual(printf_parts(b'%7ld %7ld %7ld\n'),
                         [('ld', 7), b' ', ('ld', 7), b' ', ('ld', 7), b'\n'])
        self.assertEqual(printf_parts(b'%d|%12s|%1c'), [('d', 0), b'|', ('s', 12), b'|', ('c', 1)])

    def test_width_is_bounded_while_it_is_read(self):
        self.assertEqual(printf_parts(b'%65536d'), [('d', 65536)])
        for fmt in (b'%65537d', b'%99999999999999999999999999d'):
            with self.subTest(fmt=fmt), self.assertRaises(LibraryError) as raised:
                printf_parts(fmt)
            self.assertEqual(raised.exception.kind, 'unsupported')
            self.assertIn('field width', str(raised.exception))


class LibraryFunctionTraceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, source, events=None, *, code=200):
        response = self.client.post('/simulate', json={
            'assembly_code': source, 'input_events': events or [], 'execution_limit': 10000,
        })
        self.assertEqual(response.status_code, code, response.get_json())
        return response.get_json()

    def printf(self, fmt, *registers):
        moves = ''.join(f'mov x{index}, #{value}\n' for index, value in enumerate(registers, 1))
        return self.simulate(f'adr x0, format\n{moves}bl printf\n.rodata\nformat: .asciz "{fmt}"')

    # isspace -------------------------------------------------------------

    def test_isspace_call_returns_in_w0_and_is_explained(self):
        trace = self.simulate('mov w0, 9\nbl isspace\nmov x19, x0\nmov w0, 65\nbl isspace\n'
                              'mov x20, x0\nmov w0, -1\nbl isspace')
        states = trace['register_states']
        self.assertEqual(states[2][0], 1)
        self.assertEqual(states[5][0], 0)
        self.assertEqual(states[8][0], 0)
        self.assertEqual(states[2][30], states[1][32] + 4)
        self.assertEqual(trace['explanations'][2],
                         'isspace(9) returns 1 in w0, meaning true: 9 is a tab.')
        self.assertEqual(trace['explanations'][5],
                         "isspace(65) ('A') returns 0 in w0, meaning false: it is not a whitespace character.")
        self.assertEqual(trace['explanations'][8],
                         'isspace(EOF) returns 0 in w0: EOF is not a whitespace character.')
        # A zero return is still a write to x0, and the call makes no frame.
        self.assertIn(0, trace['register_writes'][5])
        self.assertEqual(len(trace['frame_states'][2]), 1)

    def test_isspace_outside_its_domain_stops_with_advice(self):
        source = 'adr x1, byte\nldrsb w0, [x1]\nbl isspace\n.data\nbyte: .byte 0xe9'
        trace = self.simulate(source, code=400)
        info = trace['error_info']
        self.assertEqual(trace['status']['state'], 'error')
        self.assertEqual(info['kind'], 'runtime')
        self.assertEqual(info['line'], 3)
        self.assertEqual(info['message'],
                         'isspace requires EOF (-1) or a character value from 0 to 255, but w0 holds -23.')
        self.assertIn('ldrb', info['suggestion'])
        # The steps before the call stay recorded for stepping back through.
        self.assertEqual(trace['executed_lines'], [None, 1, 2])
        self.assertEqual(trace['register_states'][-1][0] & 0xffffffff, 0xffffffe9)

    def test_source_defined_isspace_overrides_the_library(self):
        trace = self.simulate('mov w0, 32\nbl isspace\nb end\nisspace: mov x0, #7\nret\nend: nop')
        self.assertEqual(trace['register_states'][-1][0], 7)
        self.assertEqual(len(trace['frame_states'][2]), 2)

    # printf field widths ---------------------------------------------------

    def test_widths_pad_on_the_left_and_count_the_padding(self):
        trace = self.printf('%7ld %7ld %7ld\\n', 3, 12, 345)
        self.assertEqual(output(trace), '      3      12     345\n')
        self.assertEqual(trace['register_states'][-1][0], 24)
        self.assertEqual(trace['explanations'][-1], 'printf writes to stdout and returns 24 in w0.')

    def test_widths_apply_to_every_conversion(self):
        source = '''adr x0, format
mov x1, #-42
mov x2, #-1
mov x3, #7
mov x4, #0x41
adr x5, word
mov x6, #0x10
bl printf
.rodata
format: .asciz "[%5d][%11u][%3lu][%3c][%6s][%6p]"
word: .asciz "abc"'''
        trace = self.simulate(source)
        self.assertEqual(output(trace), '[  -42][ 4294967295][  7][  A][   abc][  0x10]')
        self.assertEqual(trace['register_states'][-1][0], len(output(trace)))

    def test_longer_values_are_never_truncated(self):
        trace = self.simulate('adr x0, format\nadr x9, values\nldr x1, [x9]\nldr x2, [x9, 8]\nadr x3, word\n'
                              'bl printf\n.rodata\nformat: .asciz "%3d|%1ld|%2s"\nword: .asciz "longer"\n'
                              'values: .quad 123456, -9876543210')
        self.assertEqual(output(trace), '123456|-9876543210|longer')
        self.assertEqual(trace['register_states'][-1][0], 25)

    def test_width_bounds_the_output_before_padding(self):
        trace = self.printf('%65536d', 1)
        self.assertEqual(trace['register_states'][-1][0], 65536)
        self.assertEqual(output(trace), ' ' * 65535 + '1')
        trace = self.simulate('adr x0, format\nbl printf\n.rodata\nformat: .asciz "x%65536d"', code=400)
        self.assertEqual(trace['error_info']['kind'], 'unsupported')
        self.assertIn('65536 bytes', trace['error'])
        self.assertEqual(output(trace), '')

    def test_unsupported_format_features_stay_explicit_errors(self):
        for fmt in ('%-5d', '%+d', '% d', '%#lu', '%05d', '%*d', '%5.2d', '%.3s', '%7', '%7f', '%65537d'):
            with self.subTest(fmt=fmt):
                trace = self.simulate(f'adr x0, format\nbl printf\n.rodata\nformat: .asciz "{fmt}"', code=400)
                self.assertEqual(trace['error_info']['kind'], 'unsupported')
                self.assertRegex(trace['error'], 'printf (conversion|format)')
                self.assertEqual(trace['executed_lines'], [None, 1])
                self.assertEqual(output(trace), '')

    # The word-count program --------------------------------------------------

    def test_word_count_program_counts_stdin(self):
        waiting = self.simulate(WORD_COUNT)
        self.assertEqual(waiting['status']['state'], 'waiting')
        self.assertEqual(waiting['status']['pending']['function'], 'getchar')

        text = 'Hello world\n  foo\tbar  baz\nlast'
        done = self.simulate(WORD_COUNT, [{'request_id': waiting['status']['pending']['request_id'],
                                           'text': text, 'eof': True}])
        self.assertEqual(done['status']['state'], 'completed', done.get('error'))
        lines, words, chars = text.count('\n'), len(text.split()), len(text.encode('utf-8'))
        self.assertEqual(output(done), f'{lines:7d} {words:7d} {chars:7d}\n')
        self.assertEqual(done['status']['returned']['value'], 0)

        # Stepping back: nothing is printed until the printf step, and every
        # earlier step of the first request is unchanged.
        printf_step = max(step for step, line in enumerate(done['executed_lines'])
                          if line is not None and 'bl      printf' in WORD_COUNT.split('\n')[line - 1])
        self.assertEqual(output(done, printf_step - 1), '')
        self.assertEqual(output(done, printf_step), output(done))
        for key in ('register_states', 'executed_lines'):
            self.assertEqual(done[key][:len(waiting[key])], waiting[key], key)
        calls = [explanation for explanation in done['explanations'] if explanation and explanation.startswith('isspace')]
        self.assertEqual(len(calls), len(text))


if __name__ == '__main__':
    unittest.main()
