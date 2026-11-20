"""Every runnable example on the How to use page, run through the real backend.

The page promises an expected result for each program in src/guide/examples.
These tests hold it to that promise, and fail if an example has no check.
"""
import unittest
from pathlib import Path

from app import app

EXAMPLES = Path(__file__).parent.parent / 'src' / 'guide' / 'examples'


def stdout_of(trace):
    count = trace['stdout_states'][-1]
    return bytes.fromhex(''.join(trace['stdout']['chunks'][:count])).decode()


def signed(value):
    return value - (1 << 64) if value >= 1 << 63 else value


class GuideExampleTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def run_example(self, name, inputs=()):
        source = (EXAMPLES / name).read_text()
        inputs, events = list(inputs), []
        while True:
            trace = self.client.post('/simulate', json={'assembly_code': source, 'input_events': events}).get_json()
            if trace.get('status', {}).get('state') != 'waiting':
                return source, trace
            # The page's input box sends the text and then ends input.
            events.append({'request_id': trace['status']['pending']['request_id'],
                           'text': inputs.pop(0), 'eof': True})

    def assert_returned(self, trace, value):
        self.assertEqual(trace['status']['state'], 'completed', trace['status'])
        self.assertEqual(trace['status']['returned']['function'], 'main')
        self.assertEqual(trace['status']['returned']['value'], value)

    def test_arithmetic(self):
        _, trace = self.run_example('arithmetic.s')
        final = trace['register_states'][-1]
        self.assertEqual(final[1:6], [20, 5, 25, 15, 125])
        self.assert_returned(trace, 0)

    def test_loop(self):
        source, trace = self.run_example('loop.s')
        self.assertEqual(trace['register_states'][-1][0], 15)
        branch = next(number for number, line in enumerate(source.split('\n'), 1) if 'ble' in line)
        self.assertEqual(trace['executed_lines'].count(branch), 5)
        self.assertIn('Jump to sumLoop', next(
            explanation for line, explanation in zip(trace['executed_lines'], trace['explanations'])
            if line == branch))
        self.assert_returned(trace, 15)

    def test_array(self):
        _, trace = self.run_example('array.s')
        data = bytes.fromhex(trace['sections']['versions'][trace['section_states'][-1]['.data']])
        values = [int.from_bytes(data[offset:offset + 8], 'little') for offset in range(0, 40, 8)]
        self.assertEqual(values, [3, 1, 4, 1, 9])
        self.assertEqual(trace['register_states'][-1][0], 0)
        self.assert_returned(trace, 0)

    def test_recursion(self):
        _, trace = self.run_example('recursion.s')
        deepest = max(trace['frame_states'], key=len)
        self.assertEqual([frame['name'] for frame in deepest], ['main', 'fact', 'fact', 'fact', 'fact'])
        self.assertEqual(trace['executed_lines'][1], 30)  # main's first line, not fact's
        self.assert_returned(trace, 24)

    def test_malloc(self):
        _, trace = self.run_example('malloc.s')
        sizes = [len(state) for state in trace['heap_states']]
        self.assertEqual(max(sizes), 1)
        self.assertEqual(sizes[-1], 0)
        # Just before free, the block holds 42 and 7.
        live = trace['heap_states'][sizes.index(1) + 6][0]
        allocation = trace['heap_allocations']['versions'][live]
        contents = bytes.fromhex(''.join(trace['heap_allocations']['chunks'][chunk] for chunk in allocation['chunks']))
        self.assertEqual(allocation['size'], 16)
        self.assertEqual([int.from_bytes(contents[0:8], 'little'), int.from_bytes(contents[8:16], 'little')], [42, 7])
        self.assert_returned(trace, 0)

    def test_greeting(self):
        source = (EXAMPLES / 'greeting.s').read_text()
        waiting = self.client.post('/simulate', json={'assembly_code': source}).get_json()
        self.assertEqual(waiting['status']['pending']['function'], 'fgets')
        self.assertEqual(stdout_of(waiting), 'What is your name? ')
        _, trace = self.run_example('greeting.s', ['Ada'])
        self.assertEqual(stdout_of(trace), 'What is your name? Hello, Ada!\n')
        self.assert_returned(trace, 0)

    def test_null_pointer(self):
        source, trace = self.run_example('null-pointer.s')
        failing = next(number for number, line in enumerate(source.split('\n'), 1) if 'ldr     x2, [x0]' in line)
        self.assertEqual(trace['status']['state'], 'error')
        self.assertEqual(trace['status']['error_info']['kind'], 'runtime')
        self.assertEqual(trace['status']['error_info']['line'], failing)
        # The steps before the failure are kept, so they can be inspected.
        self.assertEqual(trace['executed_lines'], [None, failing - 2, failing - 1])
        self.assertEqual(trace['register_states'][-1][:2], [0, 5])

    def test_every_example_has_a_check(self):
        checked = {name[len('test_'):] for name in dir(self) if name.startswith('test_')}
        for path in EXAMPLES.glob('*.s'):
            self.assertIn(path.stem.replace('-', '_'), checked, f'{path.name} has no test')


if __name__ == '__main__':
    unittest.main()
