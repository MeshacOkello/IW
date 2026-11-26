"""Linking a program against the bundled course code.

These programs stand in for a student's bigintadd.s with deliberately trivial
BigInt_add functions, so no working solution to the assignment lives here.
"""
import os
import shutil
import subprocess
import unittest

import linker
from app import app
from assembler import assemble_program

BUNDLE_DIRECTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'course_libraries')

# Sets oSum->lLength to 0 and reports success: every sum prints as zero.
ZERO_SUM = '''
        .global BigInt_add
BigInt_add:
        str     xzr, [x2]
        mov     w0, 1
        ret
'''

# Reports an overflow on the first addition.
ALWAYS_OVERFLOWS = '''
        .global BigInt_add
BigInt_add:
        mov     w0, 0
        ret
'''

# Uses x19 to x28 without saving them, destroying what the caller kept there.
CLOBBERS_X19 = '''
        .global BigInt_add
BigInt_add:
        mov     x19, 0
        mov     x20, 0
        mov     x21, 0
        mov     x22, 0
        mov     x23, 0
        mov     x24, 0
        mov     x25, 0
        mov     x26, 0
        mov     x27, 0
        mov     x28, 0
        str     xzr, [x2]
        mov     w0, 1
        ret
'''


def stdout_text(trace):
    return b''.join(bytes.fromhex(chunk) for chunk in trace['stdout']['chunks']).decode()


class LinkingTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, code, status=200):
        response = self.client.post('/simulate', json={'assembly_code': code})
        self.assertEqual(response.status_code, status, response.get_json().get('error'))
        return response.get_json()

    def test_programs_that_need_nothing_are_not_linked(self):
        for code in ('mov x0, 1\n', 'main:\nmov w0, 0\nret\n', 'add_numbers:\nadd x0, x0, x1\nret\n'):
            with self.subTest(code=code):
                self.assertIsNone(linker.link(assemble_program(code)))

    def test_a_function_the_course_code_needs_links_its_main(self):
        link = linker.link(assemble_program(ZERO_SUM))
        self.assertIsNotNone(link)
        self.assertEqual(link.entry, linker.bundles()[0].exports['main'])

    def test_a_program_with_its_own_main_keeps_it(self):
        link = linker.link(assemble_program('main:\nmov w0, 0\nret\n' + ZERO_SUM))
        self.assertIsNone(link)

    def test_the_course_main_runs_the_program_to_completion(self):
        trace = self.simulate(ZERO_SUM)
        self.assertEqual(trace['status']['state'], 'completed')
        self.assertEqual(trace['status']['returned']['function'], 'main')
        self.assertEqual(trace['status']['returned']['value'], 0)
        output = stdout_text(trace).splitlines()
        self.assertEqual(output[:3], ['-' * 48, 'Fibonacci number 100:', '0' * 16])
        self.assertIn('Boundary test 10: ' + '0' * 16, output)
        self.assertIn('Stress test 19b: ' + '0' * 16, output)
        self.assertEqual(output[-1], '-' * 48)

    def test_only_the_programs_own_instructions_are_steps(self):
        trace = self.simulate(ZERO_SUM)
        # fib(100) adds 99 times, the boundary tests 18 times and the stress
        # tests 40 times. Each call is three instructions, and nothing from
        # the course code is a step.
        self.assertEqual(set(trace['executed_lines'][1:]), {4, 5, 6})
        self.assertEqual(len(trace['executed_lines']) - 1, 3 * (99 + 18 + 40))
        names = {frame['name'] for frames in trace['frame_states'] for frame in frames}
        self.assertEqual(names, {'BigInt_add'})

    def test_the_first_step_is_the_first_call(self):
        trace = self.simulate(ZERO_SUM)
        registers = trace['register_states'][0]
        program = assemble_program(ZERO_SUM)
        self.assertEqual(registers[32], program.symbols['BigInt_add'])
        # The three BigInt objects are on the heap, 256 KiB each.
        self.assertEqual(len(trace['heap_states'][0]), 3)
        sizes = {trace['heap_allocations']['versions'][index]['size']
                 for index in trace['heap_states'][0]}
        self.assertEqual(sizes, {8 + 8 * 32768})
        self.assertTrue(stdout_text({'stdout': {
            'chunks': trace['stdout']['chunks'][:trace['stdout_states'][0]]}}).startswith('-' * 48))

    def test_a_return_explains_the_callers_part(self):
        trace = self.simulate(ZERO_SUM)
        self.assertEqual(
            trace['explanations'][3],
            'BigInt_add returns to its caller with w0 = 1. The caller continues, then calls '
            'BigInt_add again.')
        self.assertEqual(trace['explanations'][-1][-len('main returns 0.'):], 'main returns 0.')

    def test_exit_from_the_course_code_ends_the_run(self):
        trace = self.simulate(ALWAYS_OVERFLOWS)
        self.assertEqual(trace['status'], {'state': 'completed', 'exited': {'status': 1, 'step': 2}})
        self.assertEqual(stdout_text(trace), '-' * 48 + '\nAddition overflow\n')

    def test_a_clobbered_callee_saved_register_is_named(self):
        trace = self.simulate(CLOBBERS_X19, status=400)
        self.assertEqual(trace['status']['state'], 'error')
        self.assertIn('returned with x20, x21', trace['error_info']['suggestion'])

    def test_a_program_can_call_course_functions_from_its_own_main(self):
        trace = self.simulate('''
        .section .rodata
digits: .asciz "1f"
        .section .text
main:
        sub     sp, sp, 16
        str     x30, [sp]
        mov     x0, 7
        bl      BigInt_new
        str     x0, [sp, 8]
        adr     x1, digits
        bl      BigInt_assignFromHexStr
        ldr     x0, [sp, 8]
        ldr     x1, [x0, 8]
        ldr     x0, [sp, 8]
        bl      BigInt_free
        mov     w0, 0
        ldr     x30, [sp]
        add     sp, sp, 16
        ret
''')
        self.assertEqual(trace['status']['returned'], {'function': 'main', 'value': 0, 'step': 15})
        # The value BigInt_assignFromHexStr stored, read back by the program.
        self.assertEqual(trace['register_states'][11][1], 0x1f)
        self.assertEqual(trace['explanations'][4], 'BigInt_new runs and returns.')
        self.assertEqual({frame['name'] for frames in trace['frame_states'] for frame in frames}, {'main'})

    def test_the_checked_in_bundle_matches_its_sources(self):
        if shutil.which('clang') is None:
            self.skipTest('clang is needed to rebuild the bundle')
        with open(os.path.join(BUNDLE_DIRECTORY, 'bigint.s')) as checked_in:
            expected = checked_in.read()
        try:
            subprocess.run(['python3', os.path.join(BUNDLE_DIRECTORY, 'build.py')], check=True,
                           capture_output=True)
            with open(os.path.join(BUNDLE_DIRECTORY, 'bigint.s')) as rebuilt:
                self.assertEqual(rebuilt.read(), expected,
                                 'Run course_libraries/build.py and check in the result.')
        finally:
            with open(os.path.join(BUNDLE_DIRECTORY, 'bigint.s'), 'w') as restore:
                restore.write(expected)


class LibraryAdditionsTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, code):
        response = self.client.post('/simulate', json={'assembly_code': code})
        self.assertEqual(response.status_code, 200, response.get_json().get('error'))
        return response.get_json()

    def test_calloc_memset_and_exit(self):
        trace = self.simulate('''
main:
        mov     x0, 4
        mov     x1, 8
        bl      calloc
        mov     x19, x0
        mov     w1, 0xab
        mov     x2, 3
        bl      memset
        ldr     x2, [x19]
        mov     w0, 3
        bl      exit
        mov     w0, 0
        ret
''')
        heap = trace['heap_allocations']
        after_calloc = heap['versions'][trace['heap_states'][3][0]]
        self.assertEqual(after_calloc['size'], 32)
        self.assertEqual(''.join(heap['chunks'][index] for index in after_calloc['chunks']), '00' * 32)
        self.assertEqual(trace['register_states'][8][2], 0xababab)
        self.assertEqual(trace['status'], {'state': 'completed', 'exited': {'status': 3, 'step': 10}})
        self.assertEqual(trace['explanations'][10], 'exit(3) ends the program with exit status 3.')

    def test_register_aliases(self):
        trace = self.simulate('''
        lCount .req x19
        mov     lCount, 5
        add     x0, lCount, 2
        .unreq  lCount
        mov     x19, 1
''')
        self.assertEqual(trace['register_states'][2][0], 7)
        self.assertEqual(trace['register_states'][3][19], 1)

    def test_a_named_immediate_that_needs_a_shift(self):
        trace = self.simulate('''
        .equ    MAX_DIGITS, 32768
        mov     x0, 32768
        cmp     x0, MAX_DIGITS
        sub     x1, x0, MAX_DIGITS
''')
        self.assertEqual(trace['register_states'][2][33] >> 28, 0b0110)  # Z and C set
        self.assertEqual(trace['register_states'][3][1], 0)


if __name__ == '__main__':
    unittest.main()
