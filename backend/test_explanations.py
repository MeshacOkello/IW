"""Explanations must use the recorded values and identify simulator conventions."""
import unittest
from app import app


class ExplanationTests(unittest.TestCase):
    def trace(self, source):
        with app.test_client() as client:
            return client.post('/simulate', json={'assembly_code': source}).get_json()

    def test_arithmetic_contains_inputs_and_recorded_result(self):
        trace = self.trace('mov x1, 20\nmov x2, 5\nadd x3, x1, x2\nsub x4, x1, x2\nmul x5, x3, x2')
        self.assertEqual(trace['explanations'][3], 'x3 = 20 + 5 = 25.')
        self.assertEqual(trace['explanations'][4], 'x4 = 20 − 5 = 15.')
        self.assertEqual(trace['explanations'][5], 'x5 = 25 × 5 = 125.')

    def test_branch_reports_previous_comparison_values(self):
        trace = self.trace('mov x1, 3\ncmp x1, 5\nblt less\nmov x0, 9\nless: mov x0, 1')
        self.assertEqual(trace['explanations'][3], 'Jump to less because x1 (3) < 5.')

    def test_flags_from_arithmetic_do_not_claim_a_comparison(self):
        trace = self.trace('mov x1, 1\nsubs x1, x1, 1\nbeq equal\nmov x0, 9\nequal: mov x0, 1')
        self.assertEqual(trace['explanations'][3], 'Jump to equal because Z = 1.')

    def test_unsigned_division_keeps_unsigned_values(self):
        trace = self.trace('mov x1, -1\nmov x2, 2\nudiv x3, x1, x2')
        self.assertIn('18446744073709551615 ÷ 2 = 9223372036854775807', trace['explanations'][3])

    def test_store_contains_value_address_and_width(self):
        trace = self.trace('sub sp, sp, 16\nmov x1, 42\nstr x1, [sp]')
        self.assertEqual(trace['explanations'][3], 'Store 42 from x1 at stack address 0x8ff0 (8 bytes).')

    def test_labs_minimum_is_a_simulator_convention(self):
        trace = self.trace('mov x0, -9223372036854775808\nbl labs')
        self.assertIn('C does not define labs for this value', trace['explanations'][2])
