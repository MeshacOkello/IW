import unittest

from app import app
from assembler import AssemblyError, PAGE_SIZE, assemble_program


class SectionSimulationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def simulate(self, source):
        response = self.client.post('/simulate', json={'assembly_code': source})
        self.assertEqual(response.status_code, 200, response.get_json())
        trace = response.get_json()
        for key, series in trace.items():
            if key != 'heap_allocations':
                self.assertEqual(len(series), len(trace['register_states']))
        return trace

    def test_interleaved_sections_load_strings_and_initialize_writable_storage(self):
        source = r'''
.section .rodata, "a", @progbits
message: .asciz "H//;é\n"
.data
.byte 0, 0, 0
value: .byte 41
.bss
.zero 4
scratch: .skip 4
.text
.global entry
entry: adr x0, message
ldrb w1, [x0]
ldrb w2, [x0, #7]
adrp x3, value
add x3, x3, :lo12:value
ldrb w4, [x3]
add w4, w4, #1
strb w4, [x3]
ldrb w5, [x3]
adr x6, scratch
ldr w7, [x6]
str w4, [x6]
ldr w8, [x6]
.data
pointer: .quad message
.text
adr x9, pointer
ldr x10, [x9]
'''
        program = assemble_program(source)
        message = program.symbols['message']
        value = program.symbols['value']
        scratch = program.symbols['scratch']
        sections = {section.name: section for section in program.sections}
        self.assertEqual(sections['.rodata'].data, b'H//;\xc3\xa9\n\0')
        self.assertEqual(sections['.bss'].data, b'')
        self.assertEqual(sections['.bss'].size, 8)
        trace = self.simulate(source)
        self.assertEqual(trace['executed_lines'], [None, *range(12, 25), 28, 29])
        self.assertEqual(trace['register_states'][-1][:11], [
            message, ord('H'), 0, value, 42, 42, scratch, 0, 42, program.symbols['pointer'], message,
        ])
        self.assertIn('page containing value', trace['explanations'][4])
        accesses = [access for step in trace['memory_accesses'] for access in step]
        self.assertIn({'kind': 'write', 'address': value, 'size': 1}, accesses)
        self.assertIn({'kind': 'write', 'address': scratch, 'size': 4}, accesses)
        self.assertEqual(self.simulate(source)['register_states'][-1][7], 0)

    def test_forward_backward_and_same_page_addresses(self):
        source = '''start: nop
adr x0, ahead
adr x1, start
adr x2, .+8
adrp x3, ahead
adrp x4, start
adr x5, #-4
ahead: nop'''
        symbols = assemble_program(source).symbols
        regs = self.simulate(source)['register_states'][-1]
        self.assertEqual(regs[:6], [symbols['ahead'], symbols['start'], 0x1014, 0x1000, 0x1000, 0x1014])

    def test_page_relocations_across_text_and_data_page_boundaries(self):
        source = '''
.text
first: b later
.zero 4092
later: adrp x0, first
adrp x1, buffer
add x1, x1, :lo12:buffer
ldrb w2, [x1]
.data
.space 4097
buffer: .byte 99
'''
        program = assemble_program(source)
        self.assertEqual(program.symbols['later'], 0x2000)
        self.assertEqual(program.symbols['buffer'] % PAGE_SIZE, 1)
        trace = self.simulate(source)
        self.assertEqual(trace['register_states'][-1][:3], [0x1000, program.symbols['buffer'], 99])
        self.assertEqual(trace['instruction_numbers'], [None, 1, 2, 3, 4, 5])

    def test_literal_pool_and_inline_data_are_not_instructions(self):
        source = '''ldr x0, =0x123456789abcdef0
b resume
.ltorg
inline: .word 0xd28007e1
resume: nop
.word 0xd28007e1
mov x1, #12'''
        trace = self.simulate(source)
        self.assertEqual(trace['executed_lines'], [None, 1, 2, 5])
        self.assertEqual(trace['register_states'][-1][:2], [0x123456789ABCDEF0, 0])
        implicit = self.simulate('ldr x0, =0x123456789abcdef0')
        self.assertEqual(implicit['executed_lines'], [None, 1])
        self.assertEqual(implicit['register_states'][-1][0], 0x123456789ABCDEF0)

    def test_direct_and_indirect_branches_do_not_execute_data(self):
        for section in ('.data', '.rodata', '.bss', '.text'):
            directive = '.zero 4' if section == '.bss' else '.word 0xd28007e1'
            for branch in ('b payload', 'br x0'):
                with self.subTest(section=section, branch=branch):
                    source = f'adr x0, payload\n{branch}\nmov x1, #12\n{section}\npayload: {directive}'
                    trace = self.simulate(source)
                    self.assertEqual(trace['executed_lines'], [None, 1, 2])
                    self.assertEqual(trace['register_states'][-1][1], 0)
                    self.assertEqual(trace['register_states'][-1][32], assemble_program(source).symbols['payload'])

    def test_rodata_and_text_reject_writes(self):
        for source in (
            'adr x0, literal\nstrb w1, [x0]\n.rodata\nliteral: .byte 5',
            'entry: adr x0, entry\nstrb w1, [x0]',
        ):
            with self.subTest(source=source):
                response = self.client.post('/simulate', json={'assembly_code': source})
                self.assertEqual(response.status_code, 400)
                self.assertIn('UC_ERR_WRITE_PROT', response.get_json()['error'])

    def test_legacy_stack_and_call_trace(self):
        source = '''entry: mov x0, #41
bl work
b finish
work: stp x29, x30, [sp, #-16]!
add x0, x0, #1
ldp x29, x30, [sp], #16
ret
finish: nop'''
        trace = self.simulate(source)
        self.assertEqual(trace['executed_lines'], [None, 1, 2, 4, 5, 6, 7, 3, 8])
        self.assertEqual(trace['register_states'][-1][0], 42)
        self.assertEqual(trace['register_states'][3][31], 0x8FF0)
        self.assertEqual(trace['stack_states'][3], [
            {'address': 0x8FF0, 'size': 8, 'value': 0},
            {'address': 0x8FF8, 'size': 8, 'value': 0x1008},
        ])
        self.assertEqual(trace['stack_states'][5], [])
        self.assertEqual([frame['name'] for frame in trace['frame_states'][3]], ['entry', 'work'])
        self.assertEqual([frame['name'] for frame in trace['frame_states'][6]], ['entry'])

    def test_semicolons_constants_and_original_source_lines(self):
        trace = self.simulate('''/* intro
comment */
.equ N, 3
.text
start: mov x0, #N; mov x1, #4 // comment
add x2, x0, x1''')
        self.assertEqual(trace['executed_lines'], [None, 5, 5, 6])
        self.assertEqual(trace['register_states'][-1][:3], [3, 4, 7])
        self.assertIn('x1', trace['explanations'][2])
        redefined = self.simulate('.set n, 1\nmov x0, #n\n.set n, 2\nmov x1, #n')
        self.assertEqual(redefined['register_states'][-1][:2], [1, 2])

    def test_data_only_and_empty_programs_have_one_snapshot(self):
        for source in ('', '.data\nmessage: .asciz "Hi"', '.bss\n.zero 8'):
            trace = self.simulate(source)
            self.assertEqual(trace['executed_lines'], [None])

    def test_cross_section_data_symbols_and_alignment(self):
        source = '''.data
.byte 1
.balign 8
table: .quad callback, message
.rodata
message: .asciz "ok"
.text
callback: adr x0, table
ldr x1, [x0]
ldr x2, [x0, #8]'''
        program = assemble_program(source)
        regs = self.simulate(source)['register_states'][-1]
        self.assertEqual(regs[:3], [program.symbols[name] for name in ('table', 'callback', 'message')])
        self.assertEqual(regs[0] % 8, 0)

    def test_native_literal_label_loads_and_low12_memory_operands(self):
        source = """ldr x0, number
ldr x1, =number
adrp x2, number
ldr x3, [x2, :lo12:number]
.rodata
.quad 0
number: .quad 0x123456789abcdef0"""
        number = assemble_program(source).symbols['number']
        regs = self.simulate(source)['register_states'][-1]
        self.assertEqual(regs[:4], [0x123456789ABCDEF0, number, number & -PAGE_SIZE, 0x123456789ABCDEF0])

    def test_conditional_loop_preserves_repeated_steps_and_flags(self):
        trace = self.simulate("""mov x0, #3
loop: subs x0, x0, #1
b.ne loop
ret""")
        self.assertEqual(trace['executed_lines'], [None, 1, 2, 3, 2, 3, 2, 3, 4])
        self.assertEqual(trace['register_states'][-1][0], 0)
        self.assertTrue(trace['register_states'][-1][33] & (1 << 30))

    def test_invalid_inputs_have_assembly_errors(self):
        cases = {
            'adr x0, missing': 'symbol',
            'adrp x0, #7': 'unaligned',
            '.data\nfoo: .zero 1048576\n.rodata\ntarget: .byte 1\n.text\nadr x0, target': 'out of range',
            '.data\nfoo: .byte 0\n.text\nfoo: nop': 'duplicate label',
            '.bss\n.space 2, 1': 'zero-filled',
            '.bss\n.asciz "text"': 'zero-filled',
            '.data\nnop': 'belong in .text',
            '.section .custom\n.byte 0': 'unsupported section',
            '.byte 1\nnop': 'aligned',
            '.space 28672\nnop': 'below the stack',
            '.include "file"': 'unsupported directive',
        }
        for source, error in cases.items():
            with self.subTest(source=source):
                with self.assertRaisesRegex(AssemblyError, error):
                    assemble_program(source)
                response = self.client.post('/simulate', json={'assembly_code': source})
                self.assertEqual(response.status_code, 400)
                self.assertRegex(response.get_json()['error'], error)


if __name__ == '__main__':
    unittest.main()
