"""Conservative provenance for register values whose address origin is known."""
from instruction_parser import BRANCH_ALIASES

SP = 31
PC = 32

NO_GPR_WRITE = set(BRANCH_ALIASES.values()) | {
    'b', 'br', 'ret', 'cbz', 'cbnz', 'tbz', 'tbnz', 'cmp', 'cmn', 'tst', 'nop',
    'b.mi', 'b.pl', 'b.vs', 'b.vc', 'b.al', 'b.nv',
}
WRITES_FIRST = {
    'mov', 'movz', 'movn', 'movk', 'add', 'adds', 'sub', 'subs', 'neg',
    'mul', 'madd', 'msub', 'sdiv', 'udiv', 'and', 'ands', 'orr', 'eor',
    'lsl', 'lsr', 'asr', 'mvn', 'csel', 'cset', 'cinc', 'csinc',
    'ldrb', 'ldrh', 'ldrsb', 'ldrsh', 'ldrsw', 'ldur', 'ldurb', 'ldurh',
}
STORES = {'str', 'strb', 'strh', 'stur', 'sturb', 'sturh', 'stp', 'stnp'}


def pointer_registers_after(before, word, parsed, symbols, after, *, link, library_call):
    pointers = set(before)
    destination = word & 31
    if link:
        pointers.add(30)
        if library_call and library_call != 'free':
            pointers.discard(0)
            if library_call in ('malloc', 'fgets') and after[0]:
                pointers.add(0)
    elif word & 0x1F000000 == 0x10000000:  # ADR / ADRP
        if destination != 31:
            pointers.add(destination)
    elif word & 0xFFE0FFE0 == 0xAA0003E0:  # MOV Xd, Xm (ORR with XZR)
        if destination != 31:
            pointers.discard(destination)
            source = (word >> 16) & 31
            if source != 31 and source in before:
                pointers.add(destination)
    elif word & 0x9F800000 == 0x91000000:  # 64-bit ADD/SUB (immediate)
        if destination != 31:
            pointers.discard(destination)
            if ((word >> 5) & 31) in before:
                pointers.add(destination)
    elif parsed:
        mnemonic, operands = parsed['mnemonic'], parsed['operands']
        if mnemonic in NO_GPR_WRITE or (mnemonic in STORES and operands is not None):
            # Store writeback adds an offset to its base and preserves existing
            # provenance. Using an ordinary integer as a base does not tag it.
            pass
        elif operands and mnemonic in WRITES_FIRST | {'ldr', 'ldp', 'ldnp'}:
            destinations = operands[:2] if mnemonic in {'ldp', 'ldnp'} else operands[:1]
            for register in destinations:
                if register['kind'] == 'reg':
                    pointers.discard(register['number'])
            if mnemonic == 'ldr' and len(operands) == 2:
                register, source = operands
                literal = source.get('text', '')
                label = literal[1:].strip() if literal.startswith('=') else ''
                if (register.get('bits') == 64 and register.get('number') is not None
                        and label in symbols and after[register['number']] == symbols[label]):
                    pointers.add(register['number'])
        else:
            # An unsupported instruction may overwrite registers even when
            # their numerical values do not change.
            pointers.clear()
    else:
        pointers.clear()
    return sorted(pointers | {SP, PC})
