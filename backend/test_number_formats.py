import unittest

from app import app


class NumberFormatMetadataTests(unittest.TestCase):
    def load(self, source):
        response = app.test_client().post('/simulate', json={'assembly_code': source})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def test_pointer_provenance_is_independent_of_the_register_value(self):
        trace = self.load('''adr x1, label
mov x2, x1
mov x3, #0x1020
mov w2, w2
mov x1, #0x1020
mov x4, sp
sub x5, x4, #16
eor x5, x5, xzr
label: nop''')
        pointers = trace['pointer_states']
        self.assertEqual(pointers[0], [31, 32])
        self.assertEqual(pointers[1], [1, 31, 32])
        self.assertEqual(pointers[2], [1, 2, 31, 32])
        self.assertEqual(trace['register_states'][3][1:4], [0x1020] * 3)
        self.assertNotIn(3, pointers[3])
        self.assertNotIn(2, pointers[4])
        self.assertNotIn(1, pointers[5])
        self.assertEqual(pointers[7], [4, 5, 31, 32])
        self.assertEqual(pointers[8], [4, 31, 32])
        self.assertEqual(trace['register_states'][7][5], trace['register_states'][8][5])

    def test_page_addresses_literal_symbols_and_malloc_keep_address_origins(self):
        trace = self.load('''adrp x5, item
add x5, x5, :lo12:item
ldr x6, =item
ldr x7, [x5]
mov x0, #8
bl malloc
mov x19, x0
str x5, [x19]
bl free
mov x0, #0x4000
bl malloc
.data
.quad 0
item: .quad 0x9008''')
        pointers = trace['pointer_states']
        self.assertIn(5, pointers[1])
        self.assertEqual(pointers[4], [5, 6, 31, 32])
        self.assertEqual(trace['register_states'][4][5:8], [0x9008] * 3)
        self.assertEqual(pointers[6], [0, 5, 6, 30, 31, 32])
        self.assertEqual(pointers[8], pointers[9])
        self.assertIn(19, pointers[-1])
        self.assertNotIn(0, pointers[-1])
        self.assertEqual(trace['register_states'][-1][0], 0)

    def test_untracked_instruction_drops_provenance_even_if_bits_match(self):
        trace = self.load('adr x0, label\nrbit x0, x0\nrbit x0, x0\nlabel: nop')
        self.assertIn(0, trace['pointer_states'][1])
        self.assertNotIn(0, trace['pointer_states'][2])
        self.assertNotIn(0, trace['pointer_states'][3])
        self.assertEqual(trace['register_states'][1][0], trace['register_states'][3][0])

    def test_explanations_type_addresses_and_data_and_keep_exact_values(self):
        trace = self.load('''sub sp, sp, #16
ldr x1, =0xfedcba9876543210
str x1, [sp]
mov x0, #8
bl malloc
mov x2, x0
mov x2, #0x400000''')
        parts = trace['explanation_parts']

        def numbers(step):
            return [part for part in parts[step] if isinstance(part, dict)]

        self.assertIn({'kind': 'address', 'value': str(0x8ff0)}, numbers(3))
        self.assertIn({'kind': 'data', 'value': '8'}, numbers(3))
        self.assertIn({'kind': 'address', 'value': str(0x400000)}, numbers(5))
        self.assertIn({'kind': 'address', 'value': str(0x400000)}, numbers(6))
        self.assertIn({'kind': 'data', 'value': str(0x400000)}, numbers(7))
        exact = str(0xfedcba9876543210)
        self.assertEqual(trace['exact_values'][3], {
            'registers': {'1': exact},
            'stack': {str(0x8ff0): exact},
        })

    def test_heap_diagnostic_includes_a_typed_address(self):
        response = app.test_client().post('/simulate', json={'assembly_code': 'mov x0, #42\nbl free'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('invalid free at 0x2a', response.get_json()['error'])
        self.assertIn({'kind': 'address', 'value': '42'}, response.get_json()['error_parts'])


if __name__ == '__main__':
    unittest.main()
