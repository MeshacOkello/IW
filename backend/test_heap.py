import unittest

from app import app
from heap import HEAP_SIZE, HEAP_START


class HeapSimulationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, code):
        response = self.client.post('/simulate', json={'assembly_code': code})
        self.assertEqual(response.status_code, 200, response.get_json())
        trace = response.get_json()
        self.assertEqual(len(trace['heap_states']), len(trace['register_states']))
        self.assertEqual(len(trace['heap_states']), len(trace['executed_lines']))
        heap = trace['heap_allocations']
        snapshots = [
            {
                'address': allocation['address'],
                'size': allocation['size'],
                'contents': ''.join(heap['chunks'][chunk_id] for chunk_id in allocation['chunks']),
            }
            for allocation in heap['versions']
        ]
        trace['heap_states'] = [
            [snapshots[index] for index in state] for state in trace['heap_states']
        ]
        return trace

    def test_allocation_store_read_free_and_reuse_have_independent_snapshots(self):
        trace = self.simulate('''mov x0, #5
bl malloc
mov x19, x0
mov w1, #0xabcd
strh w1, [x19, #2]
ldrh w2, [x19, #2]
bl free
mov x0, #5
bl malloc
strb wzr, [x0]
''')
        states = trace['heap_states']
        self.assertEqual(trace['executed_lines'], [None, *range(1, 11)])
        self.assertEqual(states[0], [])
        self.assertEqual(states[2], [{'address': HEAP_START, 'size': 5, 'contents': '??????????'}])
        self.assertEqual(states[5][0]['contents'], '????cdab??')
        self.assertEqual(states[6], states[5])
        self.assertEqual(states[7], [])
        self.assertEqual(states[9], states[2])
        self.assertEqual(states[10][0]['contents'], '00????????')

        regs = trace['register_states']
        self.assertEqual(regs[2][0], HEAP_START)
        self.assertEqual(regs[2][30:33], [0x1008, 0x9000, 0x1008])
        self.assertEqual(regs[7][30:33], [0x101c, 0x9000, 0x101c])
        self.assertEqual(regs[6][2], 0xabcd)
        self.assertEqual(trace['memory_accesses'][5], [
            {'kind': 'write', 'address': HEAP_START + 2, 'size': 2},
        ])
        self.assertEqual(trace['memory_accesses'][6], [
            {'kind': 'read', 'address': HEAP_START + 2, 'size': 2},
        ])
        self.assertEqual(len(trace['frame_states'][2]), 1)
        self.assertIn('malloc allocates', trace['explanations'][2])
        self.assertIn('free releases', trace['explanations'][7])

    def test_multiple_blocks_align_and_coalesce_for_a_larger_allocation(self):
        trace = self.simulate(f'''mov x0, #1
bl malloc
mov x19, x0
mov x0, #17
bl malloc
mov x20, x0
strb wzr, [x20, #16]
mov x0, x19
bl free
mov x0, x20
bl free
mov x0, #{HEAP_SIZE - 16}
bl malloc''')
        states = trace['heap_states']
        addresses = [block['address'] for block in states[7]]
        self.assertEqual(addresses, [HEAP_START, HEAP_START + 32])
        self.assertEqual(states[7][1]['contents'], '?' * 32 + '00')
        self.assertEqual([block['address'] for block in states[9]], [HEAP_START + 32])
        self.assertEqual(states[11], [])
        self.assertEqual(states[13][0]['address'], HEAP_START)
        self.assertEqual(states[13][0]['size'], HEAP_SIZE - 16)

    def test_chunked_history_preserves_a_store_across_a_chunk_boundary(self):
        trace = self.simulate("""mov x0, #1024
bl malloc
mov w1, #0xabcd
sturh w1, [x0, #255]
strb wzr, [x0]
nop""")
        states = trace['heap_states']
        self.assertEqual(states[4][0]['contents'][508:516], '??cdab??')
        self.assertEqual(states[5][0]['contents'][:4], '00??')
        self.assertEqual(states[6], states[5])
        self.assertEqual(len(trace['heap_allocations']['versions']), 3)
        self.assertEqual(len(trace['heap_allocations']['chunks']), 4)

    def test_zero_size_null_free_and_exhaustion(self):
        trace = self.simulate(f'''mov x0, #0
bl free
bl malloc
mov x19, x0
mov x0, #{HEAP_SIZE}
bl malloc
bl free
mov x0, x19
bl free''')
        self.assertEqual(trace['heap_states'][2], [])
        self.assertEqual(trace['heap_states'][3], [{'address': HEAP_START, 'size': 0, 'contents': ''}])
        self.assertEqual(trace['register_states'][6][0], 0)
        self.assertEqual(trace['heap_states'][6], trace['heap_states'][3])
        self.assertEqual(trace['heap_states'][-1], [])

    def test_user_definition_and_alias_keep_normal_calls(self):
        for definition in ('malloc: mov x0, #42', '.set malloc, local\nlocal: mov x0, #42'):
            with self.subTest(definition=definition):
                trace = self.simulate(f'''mov x0, #1
bl malloc
b done
{definition}
ret
done: nop''')
                self.assertTrue(all(not state for state in trace['heap_states']))
                self.assertEqual(trace['register_states'][-1][0], 42)
                self.assertEqual(len(trace['frame_states'][2]), 2)

    def test_heap_inside_a_user_function_preserves_stack_frames(self):
        trace = self.simulate('''bl get_byte
b end
get_byte: str x30, [sp, #-16]!
mov x0, #1
bl malloc
ldr x30, [sp], #16
ret
end: nop''')
        self.assertEqual(trace['executed_lines'], [None, 1, 3, 4, 5, 6, 7, 2, 8])
        self.assertEqual([frame['name'] for frame in trace['frame_states'][4]], ['entry', 'get_byte'])
        self.assertEqual(trace['register_states'][-1][0], HEAP_START)
        self.assertEqual(trace['stack_states'][-1], [])

    def test_heap_faults_report_the_failing_source_line(self):
        prefix = 'mov x0, #5\nbl malloc\nmov x19, x0\n'
        cases = {
            'mov x0, #1\nbl free': 'Line 5: invalid free',
            'add x0, x0, #1\nbl free': 'Line 5: invalid free',
            'bl free\nmov x0, x19\nbl free': 'Line 6: double free',
            'bl free\nldrb w1, [x19, #1]': 'Line 5: use-after-free',
            'bl free\nstrb wzr, [x19]': 'Line 5: use-after-free',
            'strh wzr, [x19, #4]': 'Line 4: out-of-bounds heap access',
            'ldrb w1, [x19, #5]': 'Line 4: out-of-bounds heap access',
            'ldrb w1, [x19, #32]': 'Line 4: out-of-bounds heap access',
        }
        for code, diagnostic in cases.items():
            with self.subTest(code=code):
                response = self.client.post('/simulate', json={'assembly_code': prefix + code})
                self.assertEqual(response.status_code, 400)
                self.assertIn(diagnostic, response.get_json()['error'])

    def test_no_other_undefined_library_symbols_resolve(self):
        response = self.client.post('/simulate', json={'assembly_code': 'bl gets'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('symbol', response.get_json()['error'])


if __name__ == '__main__':
    unittest.main()
