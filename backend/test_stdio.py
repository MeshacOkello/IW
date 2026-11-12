import unittest

from app import app
from heap import HEAP_START


def output(trace, step=-1):
    count = trace['stdout_states'][step]
    return bytes.fromhex(''.join(trace['stdout']['chunks'][:count])).decode('utf-8', errors='replace')


class StdioSimulationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, source, events=None, *, code=200, limit=10000):
        response = self.client.post('/simulate', json={
            'assembly_code': source, 'input_events': events or [], 'execution_limit': limit,
        })
        self.assertEqual(response.status_code, code, response.get_json())
        trace = response.get_json()
        if 'register_states' in trace:
            for key, values in trace.items():
                if isinstance(values, list) and key != 'error_parts':
                    self.assertEqual(len(values), len(trace['register_states']), key)
        return trace

    def event(self, trace, text=None):
        event = {'request_id': trace['status']['pending']['request_id']}
        event.update({'eof': True} if text is None else {'text': text})
        return event

    def assert_prefix(self, previous, next_trace):
        for key, value in previous.items():
            if isinstance(value, list):
                self.assertEqual(value, next_trace[key][:len(value)], key)
        for owner, fields in [('heap_allocations', ('chunks', 'versions')), ('sections', ('versions',)), ('stdout', ('chunks',))]:
            for field in fields:
                value = previous[owner][field]
                self.assertEqual(value, next_trace[owner][field][:len(value)], (owner, field))

    def test_prompt_scanf_and_replay_preserve_prefix_and_stdout(self):
        source = '''adr x0, prompt
bl printf
adr x0, format
adr x1, number
bl scanf
adr x0, answer
adr x1, number
ldr w1, [x1]
bl printf
.data
number: .word 0
.rodata
prompt: .asciz "Enter a number: "
format: .asciz "%d"
answer: .asciz "Value = %d\\n"'''
        waiting = self.simulate(source)
        self.assertEqual(waiting['status']['state'], 'waiting')
        self.assertEqual(waiting['status']['pending']['function'], 'scanf')
        self.assertEqual(waiting['status']['pending']['line'], 5)
        self.assertEqual(waiting['executed_lines'][-1], 4)
        self.assertEqual(output(waiting), 'Enter a number: ')
        self.assertEqual(output(waiting, 0), '')
        event = self.event(waiting, '-42')
        done = self.simulate(source, [event])
        self.assert_prefix(waiting, done)
        self.assertEqual(done['status']['state'], 'completed')
        self.assertEqual(done['register_states'][5][0], 1)
        self.assertEqual(done['executed_lines'], [None, *range(1, 10)])
        self.assertEqual(output(done), 'Enter a number: Value = -42\n')
        self.assertEqual(output(done, 5), 'Enter a number: ')
        write = done['memory_accesses'][5][-1]
        self.assertEqual(write, {'kind': 'write', 'address': 0x9000, 'size': 4})
        version = done['section_states'][5]['.data']
        self.assertEqual(done['sections']['versions'][version], 'd6ffffff')
        self.assertEqual(self.simulate(source, [event]), done)

    def test_printf_integer_widths_all_conversions_and_stack_vararg(self):
        source = '''sub sp, sp, #16
mov x8, #99
str x8, [sp]
adr x0, format
mov x1, #-1
mov x2, #-1
mov x3, #0x8000000000000000
mov x4, #-1
mov x5, #0x141
adr x6, text
adr x7, text
bl printf
.rodata
format: .asciz "%d %u %ld %lu %c %s %p %% %d"
text: .asciz "é"'''
        trace = self.simulate(source)
        self.assertRegex(output(trace), r'^-1 4294967295 -9223372036854775808 18446744073709551615 A é 0x[a-f0-9]+ % 99$')
        self.assertEqual(trace['register_states'][-1][0], len(output(trace).encode('utf-8')))
        self.assertNotIn(0, trace['pointer_states'][-1])
        self.assertIn({'kind': 'read', 'address': 0x8ff0, 'size': 8}, trace['memory_accesses'][-1])

    def test_puts_putchar_and_utf8_byte_output(self):
        trace = self.simulate('''adr x0, message
bl puts
mov x0, #0x141
bl putchar
mov x0, #0xc3
bl putchar
mov x0, #0xa9
bl putchar
.rodata
message: .asciz "<b>hi</b>"''')
        self.assertEqual(output(trace, 2), '<b>hi</b>\n')
        self.assertEqual(trace['register_states'][2][0], 0)
        self.assertEqual(trace['register_states'][4][0], ord('A'))
        self.assertEqual(output(trace, 6), '<b>hi</b>\nA�')
        self.assertEqual(output(trace), '<b>hi</b>\nAé')

    def test_getchar_buffers_bytes_and_eof_is_distinct_from_waiting(self):
        source = 'bl getchar\nmov x19,x0\nbl getchar\nmov x20,x0\nbl getchar\nmov x21,x0\nbl getchar'
        waiting = self.simulate(source)
        self.assertEqual(waiting['executed_lines'], [None])
        first = self.event(waiting, 'é')
        again = self.simulate(source, [first])
        self.assertEqual(again['register_states'][-1][19:22], [0xc3, 0xa9, 10])
        self.assertEqual(again['status']['pending']['line'], 7)
        done = self.simulate(source, [first, self.event(again)])
        self.assertEqual(done['register_states'][-1][0], 0xffffffff)
        self.assertEqual(done['status']['state'], 'completed')

    def test_fgets_heap_snapshots_bounds_and_buffered_remainder(self):
        source = '''mov x0,#8
bl malloc
mov x19,x0
mov x1,#5
mov x2,#0
bl fgets
mov x0,x19
mov x1,#4
bl fgets'''
        waiting = self.simulate(source)
        self.assertEqual(waiting['status']['pending']['function'], 'fgets')
        event = self.event(waiting, 'éabc')
        done = self.simulate(source, [event])
        self.assert_prefix(waiting, done)
        self.assertEqual(done['register_states'][6][0], HEAP_START)
        self.assertIn(0, done['pointer_states'][6])
        self.assertIn({'kind': 'write', 'address': HEAP_START, 'size': 5}, done['memory_accesses'][6])
        heap = done['heap_allocations']
        def contents(step):
            allocation = heap['versions'][done['heap_states'][step][0]]
            return ''.join(heap['chunks'][chunk] for chunk in allocation['chunks'])
        self.assertEqual(contents(6), 'c3a9616200??????')
        self.assertEqual(contents(9), '630a006200??????')
        self.assertEqual(done['status']['state'], 'completed')

    def test_fgets_one_byte_eof_and_invalid_sizes(self):
        prefix = 'adr x0, buffer\nmov x1,#1\nmov x2,#0\nbl fgets\n'
        source = prefix + 'mov x1,#4\nbl fgets\n.data\nbuffer: .space 4'
        waiting = self.simulate(source)
        self.assertEqual(waiting['executed_lines'][-1], 5)
        self.assertEqual(waiting['register_states'][4][0], 0x9000)
        eof = self.simulate(source, [self.event(waiting)])
        self.assertEqual(eof['register_states'][-1][0], 0)
        self.assertFalse(any(access['kind'] == 'write' for access in eof['memory_accesses'][-1]))
        bad = self.simulate(prefix.replace('mov x1,#1', 'mov x1,#0') + '.data\nbuffer:.space 4', code=400)
        self.assertIn('buffer size', bad['error'])

    def test_repeated_input_call_occurrences_inside_a_loop(self):
        source = 'mov x19,#3\nloop: bl getchar\nsubs x19,x19,#1\nb.ne loop'
        waiting = self.simulate(source)
        first = self.event(waiting, 'a')
        again = self.simulate(source, [first])
        self.assertEqual(waiting['status']['pending']['address'], again['status']['pending']['address'])
        self.assertNotEqual(waiting['status']['pending']['request_id'], again['status']['pending']['request_id'])
        self.assertEqual(again['executed_lines'], [None, 1, 2, 3, 4, 2, 3, 4])
        done = self.simulate(source, [first, self.event(again, 'b')])
        self.assert_prefix(again, done)
        self.assertEqual(done['register_states'][-1][0], ord('b'))

    def test_scanf_invalid_input_retains_nonmatching_byte_and_long_width(self):
        source = '''adr x0, format
adr x1, buffer
bl scanf
mov x19,x0
bl getchar
.data
buffer: .quad 0xaaaaaaaaaaaaaaaa
.rodata
format:.asciz "%ld"'''
        waiting = self.simulate(source)
        invalid = self.simulate(source, [self.event(waiting, 'no')])
        self.assertEqual(invalid['register_states'][-1][19], 0)
        self.assertEqual(invalid['register_states'][-1][0], ord('n'))
        good = self.simulate(source, [self.event(waiting, '-9223372036854775808')])
        self.assertEqual(good['register_states'][-1][19], 1)
        self.assertIn({'kind': 'write', 'address': 0x9000, 'size': 8}, good['memory_accesses'][3])
        self.assertEqual(good['register_states'][-1][0], 10)

    def test_whitespace_wait_and_eof_do_not_complete_input_prematurely(self):
        source = 'adr x0,format\nadr x1,buffer\nbl scanf\n.data\nbuffer:.word 99\n.rodata\nformat:.asciz "%d"'
        waiting = self.simulate(source)
        whitespace = self.event(waiting, '   ')
        again = self.simulate(source, [whitespace])
        self.assert_prefix(waiting, again)
        self.assertEqual(again['executed_lines'], waiting['executed_lines'])
        self.assertNotEqual(waiting['status']['pending']['request_id'], again['status']['pending']['request_id'])
        done = self.simulate(source, [whitespace, self.event(again)])
        self.assertEqual(done['register_states'][-1][0], 0xffffffff)
        self.assertFalse(any(access['kind'] == 'write' for access in done['memory_accesses'][-1]))

    def test_scanf_input_writes_to_stack_snapshots(self):
        source = 'sub sp,sp,#16\nadr x0,format\nmov x1,sp\nbl scanf\n.rodata\nformat:.asciz "%d"'
        waiting = self.simulate(source)
        trace = self.simulate(source, [self.event(waiting, '42')])
        self.assertEqual(trace['stack_states'][-1][0], {'address': 0x8ff0, 'size': 4, 'value': 42})
        self.assertIn({'kind': 'write', 'address': 0x8ff0, 'size': 4}, trace['memory_accesses'][-1])
        self.assertEqual(len(trace['frame_states'][-1]), 1)
        self.assertIn('scanf returns', trace['explanations'][-1])

    def test_unsupported_printf_formats_are_explicit_errors(self):
        for fmt in ('%f', '%lld', '%02d', '%.2d', '%ls', '%hhu', '%*d', '%n', '%'):
            with self.subTest(fmt=fmt):
                trace = self.simulate(f'adr x0,format\nbl printf\n.rodata\nformat:.asciz "{fmt}"', code=400)
                self.assertIn('unsupported', trace['error'])
                self.assertEqual(trace['status']['state'], 'error')
                self.assertEqual(trace['executed_lines'], [None, 1])
                self.assertEqual(output(trace), '')

    def test_invalid_strings_buffers_and_read_only_protection(self):
        invalid = self.simulate('mov x0,#1\nbl puts', code=400)
        self.assertIn('invalid', invalid['error'])
        unterminated = self.simulate('adr x0,text\nbl puts\n.data\ntext:.ascii "abc"', code=400)
        self.assertIn('unterminated', unterminated['error'])
        for directive in ('.rodata', '.text'):
            source = f'adr x0,buffer\nmov x1,#4\nmov x2,#0\nbl fgets\n{directive}\nbuffer:.asciz "abc"'
            waiting = self.simulate(source)
            failed = self.simulate(source, [self.event(waiting, 'ab')], code=400)
            self.assertIn('read-only', failed['error'])
            self.assertEqual(failed['executed_lines'], waiting['executed_lines'])

    def test_heap_bounds_and_use_after_free_apply_to_library_memory(self):
        source = 'mov x0,#2\nbl malloc\nmov x1,#4\nmov x2,#0\nbl fgets'
        waiting = self.simulate(source)
        failed = self.simulate(source, [self.event(waiting, 'abc')], code=400)
        self.assertIn('out-of-bounds', failed['error'])
        self.assert_prefix(waiting, failed)
        freed = self.simulate('mov x0,#8\nbl malloc\nbl free\nbl puts', code=400)
        self.assertIn('use-after-free', freed['error'])

    def test_scanf_range_checks_and_leading_zeroes(self):
        source = 'adr x0,format\nadr x1,buffer\nbl scanf\n.data\nbuffer:.word 0\n.rodata\nformat:.asciz "%d"'
        waiting = self.simulate(source)
        trace = self.simulate(source, [self.event(waiting, '0' * 100 + '42')])
        self.assertEqual(trace['register_states'][-1][0], 1)
        for value in ('2147483648', '-2147483649'):
            with self.subTest(value=value):
                bad = self.simulate(source, [self.event(waiting, value)], code=400)
                self.assertIn('destination type range', bad['error'])
        unsupported = self.simulate(source.replace('%d', '%u'), code=400)
        self.assertIn('exactly one', unsupported['error'])

    def test_scanf_trailing_whitespace_waits_and_preserves_next_character(self):
        source = 'adr x0,format\nadr x1,buffer\nbl scanf\nbl getchar\n.data\nbuffer:.word 0\n.rodata\nformat:.asciz "%d "'
        waiting = self.simulate(source)
        number = self.event(waiting, '42')
        again = self.simulate(source, [number])
        self.assertEqual(again['status']['state'], 'waiting')
        self.assert_prefix(waiting, again)
        trace = self.simulate(source, [number, self.event(again, 'X')])
        self.assertEqual(trace['register_states'][3][0], 1)
        self.assertEqual(trace['register_states'][4][0], ord('X'))

    def test_student_defined_stdio_function_keeps_normal_call_frames(self):
        trace = self.simulate('bl printf\nb end\nprintf: mov x0,#42\nret\nend:nop')
        self.assertEqual(trace['register_states'][-1][0], 42)
        self.assertEqual(len(trace['frame_states'][1]), 2)
        self.assertEqual(output(trace), '')

    def test_getchar_newline_and_eof_actions_keep_the_text_and_remainder(self):
        source = 'bl getchar\nmov x19,x0\nbl getchar\nmov x20,x0\nbl getchar\nmov x21,x0\nbl getchar'
        waiting = self.simulate(source)
        newline = self.event(waiting, 'A')
        again = self.simulate(source, [newline])
        self.assertEqual(again['register_states'][-1][19:21], [ord('A'), 10])
        eof = {**self.event(again), 'text': 'B'}
        done = self.simulate(source, [newline, eof])
        self.assert_prefix(again, done)
        self.assertEqual(done['register_states'][-1][21], ord('B'))
        self.assertEqual(done['register_states'][-1][0], 0xffffffff)
        empty_line = self.simulate('bl getchar', [self.event(self.simulate('bl getchar'), '')])
        self.assertEqual(empty_line['register_states'][-1][0], 10)
        empty_eof = self.simulate('bl getchar', [self.event(self.simulate('bl getchar'))])
        self.assertEqual(empty_eof['register_states'][-1][0], 0xffffffff)

    def test_fgets_newline_eof_and_empty_actions(self):
        source = 'adr x0,buffer\nmov x1,#8\nmov x2,#0\nbl fgets\n.data\nbuffer:.space 8'
        waiting = self.simulate(source)
        for text, eof, expected, result in (
            ('abc', False, b'abc\n\0', 0x9000),
            ('abc', True, b'abc\0', 0x9000),
            ('', False, b'\n\0', 0x9000),
            ('', True, b'', 0),
        ):
            with self.subTest(text=text, eof=eof):
                event = self.event(waiting, text)
                if eof:
                    event['eof'] = True
                trace = self.simulate(source, [event])
                self.assert_prefix(waiting, trace)
                self.assertEqual(trace['register_states'][-1][0], result)
                writes = [access for access in trace['memory_accesses'][-1] if access['kind'] == 'write']
                self.assertEqual([access['size'] for access in writes], [len(expected)] if expected else [])
                contents = trace['sections']['versions'][trace['section_states'][-1]['.data']]
                self.assertEqual(bytes.fromhex(contents)[:len(expected)], expected)

    def test_fgets_drains_text_before_sticky_eof_and_scanf_accepts_final_number(self):
        source = 'adr x0,buffer\nmov x1,#3\nmov x2,#0\nbl fgets\nbl fgets\nbl fgets\n.data\nbuffer:.space 8'
        waiting = self.simulate(source)
        event = {**self.event(waiting), 'text': 'abc'}
        trace = self.simulate(source, [event])
        self.assertEqual([snapshot[0] for snapshot in trace['register_states'][4:]], [0x9000, 0x9000, 0])
        self.assertEqual([access['size'] for access in trace['memory_accesses'][5] if access['kind'] == 'write'], [2])
        contents = trace['sections']['versions'][trace['section_states'][5]['.data']]
        self.assertTrue(contents.startswith('630000'))
        number = 'adr x0,format\nadr x1,buffer\nbl scanf\nmov x19,x0\nbl getchar\n.data\nbuffer:.word 0\n.rodata\nformat:.asciz "%d"'
        waiting = self.simulate(number)
        trace = self.simulate(number, [{**self.event(waiting), 'text': '42'}])
        self.assertEqual(trace['register_states'][-1][19], 1)
        self.assertEqual(trace['register_states'][-1][0], 0xffffffff)

    def test_prompt_window_excludes_output_before_completed_input(self):
        source = 'adr x0,prompt\nbl printf\nbl getchar\nbl getchar\nbl getchar\n.rodata\nprompt:.asciz "Enter your name: "'
        waiting = self.simulate(source)
        self.assertEqual(waiting['status']['pending']['stdout_start'], 0)
        again = self.simulate(source, [self.event(waiting, 'A')])
        self.assertEqual(again['status']['state'], 'waiting')
        self.assertEqual(again['status']['pending']['stdout_start'], 1)
        self.assertEqual(output(again), 'Enter your name: ')

    def test_statuses_limits_errors_and_input_protocol(self):
        self.assertEqual(self.simulate('nop')['status']['state'], 'completed')
        limited = self.simulate('again:b again', limit=3)
        self.assertEqual(limited['status']['state'], 'execution_limit')
        self.assertEqual(len(limited['executed_lines']), 4)
        partial = self.simulate('mov x0,#65\nbl putchar\nmov x0,#1\nbl puts', code=400)
        self.assertEqual(output(partial), 'A')
        self.assertEqual(partial['status']['state'], 'error')
        wrong = self.simulate('bl getchar', [{'request_id': 'wrong', 'text': 'a'}], code=400)
        self.assertIn('occurrence', wrong['error'])
        waiting = self.simulate('bl getchar')
        event = self.event(waiting, 'a')
        duplicate = self.simulate('bl getchar', [event, event], code=400)
        self.assertIn('beyond', duplicate['error'])


if __name__ == '__main__':
    unittest.main()
