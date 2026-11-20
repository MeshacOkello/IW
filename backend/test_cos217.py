"""COS 217 conventions: .equ operands, .size, main as the entry point, labs.

euclid.s is the course's own program, kept byte for byte in fixtures/ as an
end-to-end regression test.
"""
import unittest
from pathlib import Path

from app import app
from assembler import AssemblyError, assemble_program

EUCLID = (Path(__file__).parent / 'fixtures' / 'euclid.s').read_text()
LONG_MIN = -(1 << 63)


def line_of(source, text, start=1):
    """The 1-based number of the first line at or after `start` containing `text`."""
    for number, line in enumerate(source.split('\n'), 1):
        if number >= start and text in line:
            return number
    raise AssertionError(text)


def stdout_of(trace, step=-1):
    count = trace['stdout_states'][step]
    return bytes.fromhex(''.join(trace['stdout']['chunks'][:count])).decode()


class Cos217Case(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, source, inputs=(), code=200):
        """Run to the end, answering each input request with the next input."""
        inputs = list(inputs)
        events = []
        while True:
            response = self.client.post('/simulate', json={'assembly_code': source, 'input_events': events})
            trace = response.get_json()
            if trace.get('status', {}).get('state') != 'waiting':
                self.assertEqual(response.status_code, code, trace)
                return trace
            self.assertTrue(inputs, 'the program asked for more input than the test gave')
            events.append({'request_id': trace['status']['pending']['request_id'], 'text': inputs.pop(0)})

    def assembly_error(self, source):
        with self.assertRaises(AssemblyError) as caught:
            assemble_program(source)
        return caught.exception


class EuclidTests(Cos217Case):
    def run_euclid(self, first, second):
        return self.simulate(EUCLID, [f'{first}\n', f'{second}\n'])

    def test_gcd_of_signed_inputs_and_zeroes(self):
        cases = [(18, 12, 6), (-18, 12, 6), (12, -18, 6), (-18, -12, 6), (0, 7, 7), (7, 0, 7), (0, 0, 0)]
        for first, second, expected in cases:
            with self.subTest(first=first, second=second):
                trace = self.run_euclid(first, second)
                self.assertEqual(stdout_of(trace),
                                 f'Enter an integer: Enter an integer: The gcd is {expected}\n')
                self.assertEqual(trace['status'], {
                    'state': 'completed',
                    'returned': {'function': 'main', 'value': 0, 'step': len(trace['register_states']) - 1},
                })

    def test_starts_at_main_and_ends_on_its_return(self):
        trace = self.run_euclid(18, 12)
        main_line = line_of(EUCLID, 'sub     sp, sp, MAIN_STACK_BYTECOUNT')
        self.assertEqual(trace['executed_lines'][1], main_line)
        self.assertEqual(trace['executed_lines'][-1], line_of(EUCLID, '        ret', main_line))
        self.assertEqual(trace['frame_states'][0][0]['name'], 'main')
        self.assertIn('main hands control back to the system', trace['explanations'][-1])

    def test_waits_for_each_scanf_and_shows_the_prompt_first(self):
        waiting = self.client.post('/simulate', json={'assembly_code': EUCLID}).get_json()
        self.assertEqual(waiting['status']['state'], 'waiting')
        self.assertEqual(waiting['status']['pending']['function'], 'scanf')
        self.assertEqual(stdout_of(waiting), 'Enter an integer: ')

    def test_gcd_gets_its_own_stack_frame_with_named_offsets(self):
        trace = self.run_euclid(-18, 12)
        depths = [len(frames) for frames in trace['frame_states']]
        self.assertEqual(max(depths), 2)
        inside = depths.index(2)
        self.assertEqual([frame['name'] for frame in trace['frame_states'][inside]], ['main', 'gcd'])
        # The gcd frame is GCD_STACK_BYTECOUNT bytes once its prolog has run.
        frame = trace['frame_states'][inside + 1][1]
        self.assertEqual(frame['stack_end'] - frame['stack_start'], 48)
        self.assertEqual(depths[-1], 1)

        store_first = line_of(EUCLID, 'str     x0, [sp, LFIRST]')
        step = trace['executed_lines'].index(store_first)
        self.assertIn('SP + LFIRST, and LFIRST is 40', trace['explanations'][step])
        sp = trace['register_states'][step][31]
        self.assertIn({'kind': 'write', 'address': sp + 40, 'size': 8}, trace['memory_accesses'][step])

    def test_labs_is_called_and_explained(self):
        trace = self.run_euclid(-18, 12)
        labs_line = line_of(EUCLID, 'bl      labs')
        step = trace['executed_lines'].index(labs_line)
        self.assertEqual(trace['register_states'][step][0], 18)
        self.assertIn('absolute value of -18, which is 18', trace['explanations'][step])
        # The call returns to the next line of gcd.
        self.assertEqual(trace['executed_lines'][step + 1], labs_line + 1)

    def test_every_recorded_step_maps_to_its_source_line(self):
        trace = self.run_euclid(18, 12)
        source_lines = EUCLID.split('\n')
        for step, line in enumerate(trace['executed_lines'][1:], 1):
            text = source_lines[line - 1].split('//')[0].strip()
            self.assertTrue(text and not text.startswith('.'), (step, line, text))


class ConstantOperandTests(Cos217Case):
    def test_equ_names_work_as_immediates_and_offsets_without_hash(self):
        trace = self.simulate('''.equ FRAME, 32
.equ SLOT, 24
.equ VALUE, 7
sub sp, sp, FRAME
mov x0, VALUE
str x0, [sp, SLOT]
add x1, sp, SLOT
ldr x2, [x1]
add sp, sp, FRAME''')
        final = trace['register_states'][-1]
        self.assertEqual(final[2], 7)
        self.assertEqual(final[1], 0x9000 - 32 + 24)
        self.assertEqual(final[31], 0x9000)
        self.assertIn('x1 = SP + SLOT (24)', trace['explanations'][4])

    def test_hash_forms_and_expressions_still_work(self):
        trace = self.simulate('.equ N, 8\nmov x0, #N\nsub sp, sp, #(N*2)\nstr x0, [sp, #N]\nadd sp, sp, 16')
        self.assertEqual(trace['register_states'][-1][0], 8)
        self.assertIn({'kind': 'write', 'address': 0x9000 - 16 + 8, 'size': 8}, trace['memory_accesses'][3])

    def test_a_redefined_constant_keeps_the_value_each_line_saw(self):
        trace = self.simulate('.set N, 8\nmov x0, N\n.set N, 16\nmov x1, N')
        self.assertEqual(trace['register_states'][-1][:2], [8, 16])

    def test_constant_from_another_section_resolves(self):
        trace = self.simulate('.data\n.equ COUNT, 3\nvalue: .quad 0\n.text\nmov x0, COUNT')
        self.assertEqual(trace['register_states'][-1][0], 3)

    def test_names_in_comments_and_strings_are_left_alone(self):
        trace = self.simulate('.equ N, 4\n.data\nmsg: .asciz "N stays N"\n.text\nmov x0, N // N here too')
        self.assertEqual(trace['register_states'][-1][0], 4)
        message = next(section for section in trace['sections']['layout'] if section['name'] == '.data')
        contents = bytes.fromhex(trace['sections']['versions'][trace['section_states'][-1]['.data']])
        self.assertEqual(contents[:10], b'N stays N\0')
        self.assertEqual(message['size'], 10)

    def test_undefined_constant_is_reported_by_name_not_as_syntax(self):
        cases = {
            '.equ SIZE, 16\nsub sp, sp, SIZ': (2, 'SIZ', 'SIZE'),
            '.equ OFFSET, 8\nsub sp, sp, 16\nstr x0, [sp, OFFST]': (3, 'OFFST', 'OFFSET'),
            # Matching is by whole name: L10 is not L1.
            '.equ L1, 8\nsub sp, sp, 16\nadd x1, sp, L10': (3, 'L10', None),
        }
        for source, (line, name, alternative) in cases.items():
            with self.subTest(source=source):
                error = self.assembly_error(source)
                self.assertEqual(error.line, line)
                self.assertEqual(error.message, f'The label "{name}" is used here but never defined.')
                if alternative:
                    self.assertEqual(error.suggestion, f'Did you mean "{alternative}"?')

    def test_invalid_operand_syntax_is_still_syntax(self):
        error = self.assembly_error('.equ N, 8\nadd x1, N, sp')
        self.assertEqual(error.line, 2)
        self.assertIn('Wrong syntax', error.message)

    def test_constant_used_before_its_definition_names_the_problem(self):
        error = self.assembly_error('mov x0, LATER\n.equ LATER, 5')
        self.assertEqual(error.line, 1)
        self.assertEqual(error.message, 'This line uses "LATER" before the .equ line that defines it.')

    def test_error_after_constants_points_at_the_real_line(self):
        # The original report: every .equ line was fine, but the section
        # failed on an unknown call, and the first constant user was blamed.
        error = self.assembly_error(EUCLID.replace('bl      labs', 'bl      labz', 1))
        self.assertEqual(error.line, line_of(EUCLID, 'bl      labs'))
        self.assertEqual(error.message, 'The label "labz" is used here but never defined.')
        self.assertEqual(error.suggestion, 'Did you mean "labs"?')


class DirectiveAndEntryTests(Cos217Case):
    def test_size_is_metadata_and_does_not_shift_lines(self):
        source = '''helper:
    mov x0, 5
    ret
    .size helper, (. - helper)
    .type main, %function
    .global main
main:
    mov x19, x30
    bl helper
    mov x30, x19
    ret
    .size main, (. - main)'''
        program = assemble_program(source)
        self.assertEqual([statement.line for _, statement in sorted(program.instructions.items())],
                         [2, 3, 8, 9, 10, 11])
        trace = self.simulate(source)
        self.assertEqual(trace['executed_lines'], [None, 8, 9, 2, 3, 10, 11])
        self.assertEqual(trace['status']['returned'], {'function': 'main', 'value': 5, 'step': 6})

    def test_string_section_and_global_directives(self):
        program = assemble_program('.section .rodata\ngreeting: .string "hi"\n.section .text\n.global main\nmain: adr x0, greeting')
        rodata = next(section for section in program.sections if section.name == '.rodata')
        self.assertEqual(rodata.data, b'hi\0')
        self.assertEqual(program.owners['greeting'], '.rodata')

    def test_unsupported_directive_is_rejected_by_name(self):
        error = self.assembly_error('.macro twice\nmov x0, 1')
        self.assertEqual(error.message, '".macro" is not a directive the simulator supports.')

    def test_return_from_main_reports_its_int_result(self):
        trace = self.simulate('main:\n    mov w0, -3\n    ret')
        self.assertEqual(trace['status'], {'state': 'completed',
                                           'returned': {'function': 'main', 'value': -3, 'step': 2}})
        self.assertIn('main returned -3 in w0', trace['explanations'][2])

    def test_program_without_main_still_ends_at_end_of_text(self):
        trace = self.simulate('mov x0, 1\nmov x1, 2')
        self.assertEqual(trace['status'], {'state': 'completed'})
        self.assertEqual(trace['executed_lines'], [None, 1, 2])

    def test_nested_returns_do_not_end_the_program(self):
        trace = self.simulate('''main:
    sub sp, sp, 16
    str x30, [sp]
    bl outer
    ldr x30, [sp]
    add sp, sp, 16
    ret
outer:
    sub sp, sp, 16
    str x30, [sp]
    bl inner
    ldr x30, [sp]
    add sp, sp, 16
    ret
inner:
    mov x0, 42
    ret''')
        self.assertEqual(trace['status']['returned']['value'], 42)
        self.assertEqual(max(len(frames) for frames in trace['frame_states']), 3)
        self.assertEqual(trace['executed_lines'][-1], 7)


class LabsTests(Cos217Case):
    PROGRAM = '''main:
    mov x19, x30
    ldr x0, =VALUE
    bl labs
    mov x30, x19
    ret'''

    def labs_of(self, value):
        trace = self.simulate(f'.equ VALUE, {value}\n' + self.PROGRAM)
        # Steps: mov, ldr, bl labs. The third snapshot is just after the call.
        result = trace['register_states'][3][0]
        return result - (1 << 64) if result >= 1 << 63 else result, trace

    def test_absolute_value_of_signed_longs(self):
        for value, expected in [(-5, 5), (5, 5), (0, 0), (-(1 << 63) + 1, (1 << 63) - 1)]:
            with self.subTest(value=value):
                self.assertEqual(self.labs_of(value)[0], expected)

    def test_long_min_is_returned_unchanged_and_explained(self):
        result, trace = self.labs_of(LONG_MIN)
        self.assertEqual(result, LONG_MIN)
        self.assertIn('has no positive long result', trace['explanations'][3])

    def test_a_program_that_defines_labs_runs_its_own(self):
        trace = self.simulate('''labs:
    mov x0, 99
    ret
main:
    mov x19, x30
    mov x0, -5
    bl labs
    mov x30, x19
    ret''')
        self.assertEqual(trace['executed_lines'], [None, 5, 6, 7, 2, 3, 8, 9])
        self.assertEqual(trace['status']['returned']['value'], 99)
        self.assertEqual(max(len(frames) for frames in trace['frame_states']), 2)


if __name__ == '__main__':
    unittest.main()
