"""Error reporting: every failure is JSON, classified, and survivable.

The backend must stay up and keep answering after any input a student can
type, so each case here also checks that a valid program still runs next.
"""
import json
import logging
import unittest
from unittest import mock

import app as backend_app

from app import app
from assembler import AssemblyError, assemble_program
from simulator import MAX_CALL_DEPTH

WORKING_PROGRAM = 'mov x1, #20\nmov x2, #5\nadd x3, x1, x2\n'


class ErrorReportingTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def post(self, payload, **kwargs):
        return self.client.post('/simulate', json=payload, **kwargs)

    def simulate(self, source, events=None, limit=10_000):
        return self.post({'assembly_code': source, 'input_events': events or [],
                          'execution_limit': limit})

    def error(self, response):
        """The structured error, with the invariants every error must hold."""
        self.assertEqual(response.headers['Content-Type'].split(';')[0], 'application/json')
        body = response.get_json()
        self.assertIn('error_info', body, body)
        error = body['error_info']
        self.assertIn(error['kind'],
                      ('request', 'assembly', 'unsupported', 'runtime', 'internal'))
        self.assertTrue(error['message'])
        # A student-facing message is a sentence, never a traceback.
        self.assertNotIn('Traceback', error['message'])
        self.assertNotIn('File "', error['message'])
        # The flat fields older clients read stay in step with it.
        self.assertIn(error['message'], body['error'])
        return error

    def assert_still_usable(self):
        """A failed run must not stop the next program from loading."""
        response = self.simulate(WORKING_PROGRAM)
        self.assertEqual(response.status_code, 200, response.get_json())
        trace = response.get_json()
        self.assertEqual(trace['status']['state'], 'completed')
        self.assertEqual(trace['register_states'][-1][1:4], [20, 5, 25])

    # --- the inputs that used to take the backend down --------------------

    def test_unterminated_string_is_reported_not_hung(self):
        # Keystone's lexer never returns on an unterminated string literal, so
        # this has to be caught before any source reaches it.
        for source, line in (
            ('.rodata\nmessage: .asciz "Hello\n.text\nnop\n', 2),
            ('nop\n.data\ns: .ascii "a\n', 3),
            ('.text\nnop\n', None),
        ):
            with self.subTest(source=source):
                response = self.simulate(source)
                if line is None:
                    self.assertEqual(response.status_code, 200)
                    continue
                self.assertEqual(response.status_code, 400)
                error = self.error(response)
                self.assertEqual(error['kind'], 'assembly')
                self.assertEqual(error['line'], line)
                self.assertIn('never closed', error['message'])
                self.assertIn('"', error['source_line'])
        self.assert_still_usable()

    def test_unterminated_character_literal_is_reported(self):
        response = self.simulate(".data\nv: .word '\n")
        self.assertEqual(response.status_code, 400)
        error = self.error(response)
        self.assertEqual((error['kind'], error['line']), ('assembly', 2))
        self.assertIn('character literal', error['message'])
        self.assert_still_usable()

    def test_unterminated_block_comment_is_reported(self):
        response = self.simulate('nop\nmov x0, #1 /* never closed\n')
        self.assertEqual(response.status_code, 400)
        error = self.error(response)
        self.assertEqual((error['kind'], error['line']), ('assembly', 2))
        self.assertIn('/* comment that is never closed', error['message'])
        self.assert_still_usable()

    def test_quotes_inside_comments_and_strings_still_assemble(self):
        for source in (
            "# don't worry\nmov x0, #1\n",
            "// don't worry\nmov x0, #1\n",
            '.rodata\ns: .asciz "say \\"hi\\""\n.text\nnop\n',
            '.rodata\ns: .asciz "it\'s fine"\n.text\nnop\n',
            "mov x0, #'a'\n",
            '/* a\n   multi-line comment */\nmov x0, #1\n',
        ):
            with self.subTest(source=source):
                self.assertEqual(self.simulate(source).status_code, 200)

    def test_empty_directive_arguments_are_reported_not_hung(self):
        # Keystone's parser never returns on a directive argument list with a
        # hole in it, so these are rejected before it sees them.
        for source in ('.data\nv: .word 1, ,2\n', '.data\nv: .word ,1\n',
                       '.data\nv: .word ,\n', '.data\nv: .byte 1,,2\n',
                       '.data\nv: .quad 1,\n', '.equ A, 1,\nmov x0, #A\n'):
            with self.subTest(source=source):
                response = self.simulate(source)
                self.assertEqual(response.status_code, 400)
                error = self.error(response)
                self.assertEqual(error['kind'], 'assembly')
                self.assertIn('empty argument', error['message'])
        self.assert_still_usable()

    def test_commas_inside_quoted_data_are_not_argument_separators(self):
        for source in ('.rodata\ns: .asciz "a,,b"\n.text\nnop\n',
                       '.rodata\ns: .asciz "a,\\",b"\n.text\nnop\n',
                       ".data\nv: .byte 'a', ','\n.text\nnop\n",
                       '.data\n.align 3,\nv: .word 1\n.text\nnop\n',
                       '.section .data, "aw"\nv: .quad 1\n.text\nnop\n',
                       '.type main, %function\nmain: nop\n.size main, .-main\n'):
            with self.subTest(source=source):
                self.assertEqual(self.simulate(source).status_code, 200)

    def test_a_hang_in_the_assembler_is_reported_and_the_backend_recovers(self):
        # The guards in assembler.py catch the malformed source we know about.
        # This is the backstop for the rest: Keystone runs in a worker process,
        # so a parser that never returns costs one worker, not the backend.
        import assembly_worker

        with mock.patch.object(backend_app, 'assemble_in_worker',
                               side_effect=assembly_worker.AssemblyTimeout(10)):
            response = self.post({'assembly_code': WORKING_PROGRAM})
        self.assertEqual(response.status_code, 400)
        error = self.error(response)
        self.assertEqual(error['kind'], 'assembly')
        self.assertEqual(error['detail'], 'assembler timeout')
        self.assertIn('could not finish', error['message'])
        self.assertIn('unclosed quote', error['suggestion'])
        self.assert_still_usable()

    def test_the_worker_really_is_killed_and_replaced_after_a_timeout(self):
        # Drive the worker itself, with source that genuinely does not return.
        import assembly_worker
        assembly_worker.shutdown()
        try:
            with self.assertLogs(assembly_worker.logger, level=logging.ERROR):
                with self.assertRaises(assembly_worker.AssemblyTimeout):
                    # An incomplete hex literal is one of Keystone's hangs.
                    assembly_worker.assemble_in_worker('.data\nv: .word 0x\n', timeout=4)
            # The next program is assembled by a fresh worker.
            program = assembly_worker.assemble_in_worker(WORKING_PROGRAM)
            self.assertEqual(len(program.instructions), 3)
        finally:
            assembly_worker.shutdown()
        self.assert_still_usable()

    def test_runaway_recursion_stops_with_an_error_and_keeps_its_steps(self):
        # Every recorded step holds a snapshot of every live call, so an
        # uncapped depth would grow the trace with the square of the steps.
        response = self.simulate('f:\nbl f\n')
        self.assertEqual(response.status_code, 400)
        trace = response.get_json()
        error = self.error(response)
        self.assertEqual(error['kind'], 'runtime')
        self.assertEqual(error['line'], 2)
        self.assertEqual(error['detail'], 'call depth limit')
        self.assertIn(f'{MAX_CALL_DEPTH} calls deep', error['message'])
        self.assertIn('base case', error['suggestion'])
        # The steps leading up to it are all there to step through.
        self.assertEqual(len(trace['register_states']), MAX_CALL_DEPTH + 1)
        self.assertEqual(len(trace['frame_states']), len(trace['register_states']))
        self.assertEqual(len(trace['frame_states'][-1]), MAX_CALL_DEPTH + 1)
        self.assert_still_usable()

    def test_recursion_within_the_limit_still_records_every_frame(self):
        # Three nested calls, to show the depth cap does not disturb frames.
        source = '''bl depth3
b done
depth3: stp x29, x30, [sp, #-16]!
bl depth2
ldp x29, x30, [sp], #16
ret
depth2: stp x29, x30, [sp, #-16]!
bl depth1
ldp x29, x30, [sp], #16
ret
depth1: mov x0, #7
ret
done: nop
'''
        trace = self.simulate(source).get_json()
        self.assertEqual(trace['status']['state'], 'completed')
        deepest = max(trace['frame_states'], key=len)
        self.assertEqual([frame['name'] for frame in deepest],
                         ['entry', 'depth3', 'depth2', 'depth1'])
        # A caller's frame ends where its callee entered, at every depth.
        for frames in trace['frame_states']:
            for caller, callee in zip(frames, frames[1:]):
                self.assertEqual(caller['stack_start'], callee['stack_end'])

    # --- request validation -----------------------------------------------

    def test_malformed_requests_return_json_errors(self):
        cases = [
            ({'kwargs': {'data': 'not json at all',
                         'content_type': 'application/json'}}, 'not valid JSON'),
            ({'kwargs': {'data': '{"assembly_code": "nop"}'}}, 'Content-Type'),
            ({'json': [1, 2, 3]}, 'must be a JSON object'),
            ({'json': 'nop'}, 'must be a JSON object'),
            ({'json': {}}, 'assembly_code must be a string'),
            ({'json': {'assembly_code': 42}}, 'assembly_code must be a string'),
            ({'json': {'assembly_code': None}}, 'assembly_code must be a string'),
            ({'json': {'assembly_code': 'nop', 'input_events': 'text'}}, 'input_events'),
            ({'json': {'assembly_code': 'nop', 'input_events': [1]}}, 'input_events'),
            ({'json': {'assembly_code': 'nop', 'execution_limit': 0}}, 'execution_limit'),
            ({'json': {'assembly_code': 'nop', 'execution_limit': 10_001}}, 'execution_limit'),
            ({'json': {'assembly_code': 'nop', 'execution_limit': '10'}}, 'execution_limit'),
            ({'json': {'assembly_code': 'nop', 'execution_limit': 1.5}}, 'execution_limit'),
            ({'json': {'assembly_code': 'nop', 'execution_limit': True}}, 'execution_limit'),
            ({'json': {'assembly_code': 'x' * (1 << 20) + 'y'}}, 'at most'),
        ]
        for case, expected in cases:
            with self.subTest(case=case):
                response = (self.client.post('/simulate', **case['kwargs'])
                            if 'kwargs' in case else self.post(case['json']))
                self.assertEqual(response.status_code, 400)
                error = self.error(response)
                self.assertEqual(error['kind'], 'request')
                self.assertIn(expected, error['message'])
                # A request problem is never blamed on a line of the program.
                self.assertNotIn('line', error)
        self.assert_still_usable()

    def test_unknown_route_and_method_return_json_not_html(self):
        for path, method, code in (('/simulate', 'GET', 405), ('/simulate', 'PUT', 405),
                                   ('/nope', 'GET', 404), ('/nope', 'POST', 404)):
            with self.subTest(path=path, method=method):
                response = self.client.open(path, method=method)
                self.assertEqual(response.status_code, code)
                error = self.error(response)
                self.assertEqual(error['kind'], 'request')
                self.assertEqual(error['detail'], f'HTTP {code}')

    def test_input_events_for_another_run_are_a_request_error(self):
        response = self.simulate('bl getchar\n', [{'request_id': 'stale', 'text': 'a'}])
        self.assertEqual(response.status_code, 400)
        error = self.error(response)
        self.assertEqual(error['kind'], 'request')
        self.assertIn('Load the program again', error['suggestion'])
        self.assert_still_usable()

    # --- assembly errors name the line ------------------------------------

    def test_assembly_errors_carry_the_line_and_the_source(self):
        cases = {
            'mov x1, #1\nmvo x2, #2\n': (2, 'mvo x2, #2', 'not an AArch64 instruction'),
            'nop\nnop\nb nowhere\n': (3, 'b nowhere', 'never defined'),
            'nop\nmov x1, x2, x3, x4\n': (2, 'mov x1, x2, x3, x4', 'does not allow the operands'),
            '.data\nv: .word 1\nmov x0, #1\n': (3, 'mov x0, #1', 'belong in .text'),
            'a: nop\nnop\na: nop\n': (3, 'a: nop', 'defined more than once'),
        }
        for source, (line, text, expected) in cases.items():
            with self.subTest(source=source):
                response = self.simulate(source)
                self.assertEqual(response.status_code, 400)
                error = self.error(response)
                self.assertEqual(error['kind'], 'assembly')
                self.assertEqual(error['line'], line)
                self.assertEqual(error['source_line'], text)
                self.assertIn(expected, error['message'])
                self.assertIn(f'Line {line}', response.get_json()['error'])
        self.assert_still_usable()

    def test_a_misspelling_suggests_the_intended_name(self):
        error = self.error(self.simulate('mov x1, #1\nmvo x2, #2\n'))
        self.assertEqual(error['suggestion'], 'Did you mean "mov"?')
        error = self.error(self.simulate('loop: nop\nb lopo\n'))
        self.assertEqual(error['suggestion'], 'Did you mean "loop"?')

    def test_advice_is_given_only_when_it_is_derived_from_the_error(self):
        # A checklist of things to look at is not an explanation, so a message
        # the simulator cannot add anything certain to stands on its own.
        bare = self.error(self.simulate('mov x1, #20\nmov x2, 55,7\n'))
        self.assertEqual(bare['message'],
                         'Wrong syntax. AArch64 does not allow the operands of "mov" '
                         'in this form.')
        self.assertNotIn('suggestion', bare)
        for source in ('a: nop\nnop\na: nop\n',            # restates the message
                       'nop\nb nowhere\n',                  # no near label to offer
                       'mov x1, #1\nzzz x2, #2\n'):         # no near mnemonic to offer
            with self.subTest(source=source):
                self.assertNotIn('suggestion', self.error(self.simulate(source)))

        # Advice drawn from this error's own facts is still given.
        derived = {
            'loop: nop\nb lopo\n': 'Did you mean "loop"?',
            'mov x0, #0\nldr x2, [x0]\n':
                'The address is 0, so the program read through a null pointer.',
            '.rodata\nv: .word 1\n.text\nadr x0, v\nstr x0, [x0]\n':
                '.rodata is read-only. Move the data you want to change into .data or .bss.',
        }
        for source, advice in derived.items():
            with self.subTest(source=source):
                self.assertEqual(self.error(self.simulate(source))['suggestion'], advice)

    def test_unsupported_features_are_not_called_mistakes(self):
        cases = {
            '.include "other.s"\n': 'not a directive',
            '.section .custom\n.byte 0\n': 'not a section',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                error = self.error(self.simulate(source))
                self.assertEqual(error['kind'], 'unsupported')
                self.assertIn(expected, error['message'])

    # --- runtime errors keep the steps already recorded -------------------

    def test_runtime_errors_preserve_the_recorded_steps(self):
        cases = {
            'mov x1, #7\nmov x0, #0\nldr x2, [x0]\n': (3, 'UC_ERR_READ_UNMAPPED', 'null pointer'),
            '.rodata\nv: .word 1\n.text\nadr x0, v\nmov x1, #5\nstr x1, [x0]\n':
                (6, 'UC_ERR_WRITE_PROT', 'read-only'),
            'svc #0\n': (1, 'UC_ERR_EXCEPTION', None),
        }
        for source, (line, detail, advice) in cases.items():
            with self.subTest(source=source):
                response = self.simulate(source)
                self.assertEqual(response.status_code, 400)
                trace = response.get_json()
                error = self.error(response)
                self.assertEqual(error['kind'], 'runtime')
                self.assertEqual(error['line'], line)
                self.assertEqual(error['detail'], detail)
                if advice:
                    self.assertIn(advice, error['suggestion'] + error['message'])
                # Every step before the fault is still available to inspect.
                self.assertEqual(trace['status']['state'], 'error')
                self.assertGreaterEqual(len(trace['register_states']), 1)
                for key, values in trace.items():
                    if isinstance(values, list) and key not in ('error_parts',):
                        self.assertEqual(len(values), len(trace['register_states']), key)
        self.assert_still_usable()

    def test_faulting_address_is_reported_as_data_for_either_base(self):
        error = self.error(self.simulate('mov x0, #0\nldr x2, [x0]\n'))
        self.assertIn({'kind': 'address', 'value': '0'}, error['message_parts'])
        # The flat parts keep the location prefix the old clients rendered.
        parts = self.simulate('mov x0, #0\nldr x2, [x0]\n').get_json()['error_parts']
        self.assertEqual(parts[0], 'Line 2: ')

    def test_heap_faults_explain_the_mistake(self):
        cases = {
            'mov x0, #8\nbl malloc\nbl free\nbl free\n': ('double free', 'freed once'),
            'mov x0, #8\nbl malloc\nmov x1, #1\nstr x1, [x0, #64]\n':
                ('out-of-bounds heap access', 'past the end'),
            'mov x0, #8\nbl malloc\nmov x19, x0\nbl free\nldrb w1, [x19]\n':
                ('use-after-free', 'already freed'),
        }
        for source, (expected, advice) in cases.items():
            with self.subTest(source=source):
                error = self.error(self.simulate(source))
                self.assertEqual(error['kind'], 'runtime')
                self.assertIn(expected, error['message'])
                self.assertIn(advice, error['suggestion'])
        self.assert_still_usable()

    def test_execution_limit_is_not_an_error(self):
        trace = self.simulate('loop: b loop\n', limit=50).get_json()
        self.assertEqual(trace['status']['state'], 'execution_limit')
        self.assertNotIn('error_info', trace)

    # --- the simulator's own failures -------------------------------------

    def test_an_internal_failure_is_logged_and_shown_without_a_traceback(self):
        import app as backend

        def explode(*_arguments, **_keywords):
            raise RuntimeError('deliberate fault with a /secret/path.py detail')

        original = backend.assemble_in_worker
        backend.assemble_in_worker = explode
        try:
            with self.assertLogs(backend.logger, level=logging.ERROR) as logged:
                response = self.post({'assembly_code': WORKING_PROGRAM})
        finally:
            backend.assemble_in_worker = original

        self.assertEqual(response.status_code, 500)
        error = self.error(response)
        self.assertEqual(error['kind'], 'internal')
        self.assertEqual(error['detail'], 'RuntimeError')
        # The student is told it is not their program, and sees no internals.
        self.assertIn('was not the cause', error['message'])
        self.assertNotIn('deliberate fault', json.dumps(response.get_json()))
        # The traceback is kept on the server instead.
        self.assertIn('Traceback', '\n'.join(logged.output))
        self.assertIn('deliberate fault', '\n'.join(logged.output))
        self.assert_still_usable()

    def test_a_broken_explanation_does_not_discard_the_trace(self):
        import app as backend

        def explode(*_arguments, **_keywords):
            raise IndexError('explanation bug')

        original = backend.explain_trace
        backend.explain_trace = explode
        try:
            with self.assertLogs(backend.logger, level=logging.ERROR):
                response = self.post({'assembly_code': WORKING_PROGRAM})
        finally:
            backend.explain_trace = original

        self.assertEqual(response.status_code, 200)
        trace = response.get_json()
        self.assertEqual(trace['register_states'][-1][1:4], [20, 5, 25])
        self.assertEqual(trace['explanations'], [None] * len(trace['register_states']))

    # --- the assembler's own contract -------------------------------------

    def test_assembly_error_keeps_its_structured_fields(self):
        with self.assertRaises(AssemblyError) as raised:
            assemble_program('nop\nmvo x0, #1\n')
        error = raised.exception
        self.assertEqual(error.line, 2)
        self.assertEqual(str(error), f'Line 2: {error.message}')
        self.assertIn('KS_ERR_ASM_MNEMONICFAIL', error.detail)


if __name__ == '__main__':
    unittest.main()
