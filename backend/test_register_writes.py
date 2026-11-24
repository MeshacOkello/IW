import unittest
from app import app


class RegisterWriteTests(unittest.TestCase):
    def trace(self, source):
        with app.test_client() as client:
            return client.post('/simulate', json={'assembly_code': source}).get_json()

    def test_first_write_zero_and_later_clear_are_recorded(self):
        trace = self.trace('mov w0, 0\nmov x1, 20\nsub x1, x1, 20\nmov x2, 4')
        self.assertEqual(trace['register_writes'], [[], [0], [1], [1], [2]])

    def test_reads_do_not_mark_their_sources_written(self):
        trace = self.trace('sub sp, sp, 16\nstr x0, [sp]\ncmp x1, 0\nldr x2, [sp]')
        self.assertEqual(trace['register_writes'], [[], [], [], [], [2]])

    def test_library_return_zero_is_a_write(self):
        trace = self.trace('mov x0, 0\nbl labs')
        self.assertEqual(trace['register_writes'][-1], [0, 30])

    def test_failed_instruction_is_not_a_write(self):
        trace = self.trace('mov x0, 0\nldr x1, [x0]')
        self.assertEqual(trace['register_writes'], [[], [0]])
