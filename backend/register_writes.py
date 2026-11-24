"""Display metadata: distinguish a zero written by the program from initial zero."""
from instruction_parser import parse_instruction
from pointer_registers import WRITES_FIRST


FIRST_DESTINATION = WRITES_FIRST | {'ldr', 'adr', 'adrp'}
PAIR_DESTINATIONS = {'ldp', 'ldnp'}


def register_writes(statements, states, library_calls):
    writes = [[]]  # Before the first instruction, no register has been written.
    for index, statement in enumerate(statements, 1):
        before, after = states[index - 1:index + 1]
        # Numerical changes also cover instructions outside the explained subset.
        written = {reg for reg in range(31) if before[reg] != after[reg]}
        parsed = parse_instruction(statement.text)
        if parsed:
            mnemonic, operands = parsed['mnemonic'], parsed['operands']
            if mnemonic in {'bl', 'blr'}:
                written.add(30)
            if operands and mnemonic in FIRST_DESTINATION | PAIR_DESTINATIONS:
                destinations = operands[:2] if mnemonic in PAIR_DESTINATIONS else operands[:1]
                for operand in destinations:
                    if operand['kind'] == 'reg' and operand['special'] is None:
                        written.add(operand['number'])
        call = library_calls.get(before[32])
        if call and call != 'free':
            written.add(0)
        writes.append(sorted(written))
    return writes
