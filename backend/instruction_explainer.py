from instruction_parser import parse_instruction
from simulator import STACK_START, STACK_END

# Builds a plain-English explanation of one executed instruction.
# "before" and "after" are register snapshots (x0..x30, sp, pc, nzcv) taken
# around the instruction; accesses are the memory reads/writes it made.
# Results always come from the trace; the math done here is only used to
# check that the trace really matches the source line being explained.

SP, PC, NZCV = 31, 32, 33

TRACE_MISMATCH = "No explanation: the recorded trace doesn't match this line."

LOAD_SIZES = {'ldr': None, 'ldrb': 1, 'ldrh': 2, 'ldrsb': 1, 'ldrsh': 2, 'ldrsw': 4}
STORE_SIZES = {'str': None, 'strb': 1, 'strh': 2}

BRANCH_CONDITIONS = ('beq', 'bne', 'blt', 'ble', 'bgt', 'bge', 'blo', 'bls', 'bhi', 'bhs')


class Unexplained(Exception):
    pass


def mask(bits):
    return (1 << bits) - 1


def signed(value, bits):
    value &= mask(bits)
    return value - (1 << bits) if value >> (bits - 1) else value


def plural(count):
    return f"{count} byte" if count == 1 else f"{count} bytes"


def flags(registers):
    nzcv = registers[NZCV]
    return {'N': (nzcv >> 31) & 1, 'Z': (nzcv >> 30) & 1, 'C': (nzcv >> 29) & 1, 'V': (nzcv >> 28) & 1}


def flag_text(registers):
    values = flags(registers)
    return ' '.join(f"{name}={values[name]}" for name in 'NZCV')


def subtraction_flags(a, b, bits):
    result = (a - b) & mask(bits)
    return {'N': result >> (bits - 1), 'Z': int(result == 0), 'C': int(a >= b),
            'V': (((a ^ b) & (a ^ result)) >> (bits - 1)) & 1}


def addition_flags(a, b, bits):
    result = (a + b) & mask(bits)
    return {'N': result >> (bits - 1), 'Z': int(result == 0), 'C': int(a + b > mask(bits)),
            'V': ((~(a ^ b) & (a ^ result)) >> (bits - 1)) & 1}


def name(register):
    return 'SP' if register['special'] == 'sp' else register['name']


class Step:
    def __init__(self, mnemonic, operands, before, after, before_stack, accesses):
        self.mnemonic = mnemonic
        self.operands = operands
        self.before = before
        self.after = after
        self.before_stack = before_stack
        self.accesses = accesses

    def read(self, register, when):
        if register['special'] == 'zr':
            return 0
        registers = self.before if when == 'before' else self.after
        raw = registers[SP] if register['special'] == 'sp' else registers[register['number']]
        return raw & mask(register['bits'])

    # Show a register's value: addresses in hex, everything else as signed decimal
    def show(self, register, value):
        if register['special'] == 'sp' or register['number'] == 30:
            return hex(value)
        return str(signed(value, register['bits']))

    def require_next_pc(self):
        if self.after[PC] != self.before[PC] + 4:
            raise Unexplained(TRACE_MISMATCH)

    def operand(self, index, *kinds):
        if index >= len(self.operands) or self.operands[index]['kind'] not in kinds:
            raise Unexplained(f"This form of {self.mnemonic} isn't explained yet.")
        return self.operands[index]

    def count(self, *allowed):
        if len(self.operands) not in allowed:
            raise Unexplained(f"This form of {self.mnemonic} isn't explained yet.")

    # Notes about the destination register that apply to most instructions
    def destination_notes(self, destination, result):
        notes = ''
        if destination['special'] is None and self.read(destination, 'before') == result:
            notes += f" ({destination['name']} is unchanged.)"
        if destination['bits'] == 32 and destination['special'] is None:
            number = destination['number']
            if self.before[number] >> 32 and not self.after[number] >> 32:
                notes += f" Writing w{number} also clears the upper 32 bits of x{number}."
        return notes

    # The second source operand of arithmetic/logic: a register (maybe shifted)
    # or an immediate. Returns (value or None, formula text, value text).
    def second_operand(self, index, bits):
        operand = self.operand(index, 'reg', 'imm', 'label')
        if operand['kind'] == 'label':
            return None, operand['name'], operand['name']
        if operand['kind'] == 'imm':
            if len(self.operands) > index + 1:
                raise Unexplained(f"This form of {self.mnemonic} isn't explained yet.")
            if operand['value'] is None:
                return None, operand['text'], operand['text']
            return operand['value'] & mask(bits), operand['text'], operand['text']
        value = self.read(operand, 'before')
        if len(self.operands) == index + 1:
            return value, name(operand), self.show(operand, value)
        shift = self.operand(index + 1, 'shift')
        amount = shift['amount']['value']
        if amount is None or len(self.operands) > index + 2:
            raise Unexplained(f"This form of {self.mnemonic} isn't explained yet.")
        shifted = shift_value(shift['op'], value, amount, bits)
        direction = 'left' if shift['op'] == 'lsl' else 'right'
        return (shifted, f"({name(operand)} shifted {direction} by {amount})",
                f"{signed(shifted, bits)} ({self.show(operand, value)} shifted {direction} by {amount})")


def shift_value(op, value, amount, bits):
    if op == 'lsl':
        return (value << amount) & mask(bits)
    if op == 'lsr':
        return value >> amount
    return (signed(value, bits) >> amount) & mask(bits)


def explain_flags(step):
    values = flags(step.after)
    text = f" Sets flags {flag_text(step.after)}."
    if values['Z']:
        text += " Z=1 because the result is 0."
    elif values['N']:
        text += " N=1 because the result is negative."
    if values['V']:
        text += " V=1 means signed overflow: the true answer didn't fit."
    return text


def check_flags(step, expected):
    if expected != flags(step.after):
        raise Unexplained(TRACE_MISMATCH)


# ---------- moves ----------

def explain_mov(step):
    step.count(2)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    source = step.operand(1, 'reg', 'imm', 'label')
    if destination['special'] == 'sp':
        if source['kind'] != 'reg':
            raise Unexplained("This form of mov isn't explained yet.")
        old, new = step.before[SP], step.after[SP]
        return f"Set SP to the value in {name(source)}. SP moves from {hex(old)} to {hex(new)}."

    result = step.read(destination, 'after')
    shown = step.show(destination, result)
    if source['kind'] == 'reg':
        if (step.read(source, 'before') & mask(destination['bits'])) != result:
            raise Unexplained(TRACE_MISMATCH)
        if source['special'] == 'zr':
            text = f"Set {name(destination)} to 0 ({source['name']} always reads as 0)."
        else:
            if source['special'] == 'sp':
                shown = hex(result)
            text = f"Copy {name(source)} into {name(destination)}. {name(destination)} = {shown}."
    else:
        label = source['text'] if source['kind'] == 'imm' else source['name']
        value = source['value'] if source['kind'] == 'imm' else None
        if value is not None and (value & mask(destination['bits'])) != result:
            raise Unexplained(TRACE_MISMATCH)
        if value is not None and label.lstrip('-').isdigit():
            text = f"Put {shown} into {name(destination)}."
        else:
            text = f"Put {label} ({shown}) into {name(destination)}."
    return text + step.destination_notes(destination, result)


# ---------- arithmetic and logic ----------

def explain_stack_pointer_math(step, op_value):
    old, new = step.before[SP], step.after[SP]
    if op_value is not None:
        expected = (old + op_value if step.mnemonic == 'add' else old - op_value) & mask(64)
        if expected != new:
            raise Unexplained(TRACE_MISMATCH)
    if new < old:
        text = f"Allocate {old - new} bytes on the stack. SP moves from {hex(old)} to {hex(new)}."
    elif new > old:
        text = f"Release {new - old} bytes from the stack. SP moves from {hex(old)} to {hex(new)}."
    else:
        text = f"SP stays at {hex(old)}; no stack space is allocated or released."
    if new % 16:
        text += f" Note: SP should stay a multiple of 16, and {hex(new)} is not."
    return text


def explain_add_sub(step):
    step.count(3, 4)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    first = step.operand(1, 'reg')
    bits = destination['bits']
    second, second_formula, _ = step.second_operand(2, bits)
    adding = step.mnemonic in ('add', 'adds')
    sign = '+' if adding else '−'

    if step.mnemonic == 'subs' and destination['special'] == 'zr':
        return explain_compare(step, offset=1)

    if destination['special'] == 'sp' and first['special'] == 'sp' and step.mnemonic in ('add', 'sub'):
        return explain_stack_pointer_math(step, second)

    a = step.read(first, 'before')
    if destination['special'] == 'zr':
        result = ((a + second) if adding else (a - second)) & mask(bits) if second is not None else None
    else:
        result = step.read(destination, 'after')
    if second is not None and ((a + second) if adding else (a - second)) & mask(bits) != result:
        raise Unexplained(TRACE_MISMATCH)

    if step.mnemonic in ('adds', 'subs') and second is not None:
        check_flags(step, (addition_flags if adding else subtraction_flags)(a, second, bits))

    shows_address = first['special'] == 'sp' or destination['special'] == 'sp'
    text = ''
    if first['special'] == 'sp' and destination['special'] != 'sp':
        text = "Compute a stack address. "
    if destination['special'] == 'zr':
        text += f"Compute {name(first)} {sign} {second_formula} and throw the result away (xzr discards writes)."
    else:
        text += f"{name(destination)} = {name(first)} {sign} {second_formula}."
        if destination['special'] == 'sp':
            text += f" SP moves from {hex(step.before[SP])} to {hex(result)}."
        elif second is not None and not shows_address:
            exact = signed(a, bits) + signed(second, bits) if adding else signed(a, bits) - signed(second, bits)
            if exact != signed(result, bits):
                text += f" The true result doesn't fit in {bits} bits, so it wraps around."
        text += step.destination_notes(destination, result)
    if step.mnemonic in ('adds', 'subs'):
        text += explain_flags(step)
    return text


def explain_neg(step):
    step.count(2)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    source = step.operand(1, 'reg')
    bits = destination['bits']
    value = step.read(source, 'before')
    result = step.read(destination, 'after')
    if (-value) & mask(bits) != result:
        raise Unexplained(TRACE_MISMATCH)
    return (f"{name(destination)} = −{name(source)} (negate: flip the sign)."
            + step.destination_notes(destination, result))


def explain_mul(step):
    step.count(3)
    step.require_next_pc()
    destination, first, second = (step.operand(i, 'reg') for i in range(3))
    bits = destination['bits']
    a, b = step.read(first, 'before'), step.read(second, 'before')
    result = step.read(destination, 'after')
    if (a * b) & mask(bits) != result:
        raise Unexplained(TRACE_MISMATCH)
    text = f"{name(destination)} = {name(first)} × {name(second)}."
    if signed(a, bits) * signed(b, bits) != signed(result, bits):
        text += f" The full product doesn't fit in {bits} bits, so only the low {bits} bits are kept."
    return text + step.destination_notes(destination, result)


def explain_divide(step):
    step.count(3)
    step.require_next_pc()
    destination, first, second = (step.operand(i, 'reg') for i in range(3))
    bits = destination['bits']
    a, b = step.read(first, 'before'), step.read(second, 'before')
    result = step.read(destination, 'after')
    is_signed = step.mnemonic == 'sdiv'
    if is_signed:
        sa, sb = signed(a, bits), signed(b, bits)
        expected = 0 if sb == 0 else (abs(sa) // abs(sb)) * (1 if (sa < 0) == (sb < 0) else -1)
        kind = "signed division, rounds toward zero"
    else:
        expected = 0 if b == 0 else a // b
        kind = "unsigned division, rounds down"
    if expected & mask(bits) != result:
        raise Unexplained(TRACE_MISMATCH)
    text = f"{name(destination)} = {name(first)} ÷ {name(second)} ({kind})."
    if b == 0:
        text += f" {name(second)} is 0, and dividing by 0 gives 0 on AArch64; there is no error."
    return text + step.destination_notes(destination, result)


LOGIC = {
    'and': ('AND', lambda a, b: a & b, "each result bit is 1 only where both inputs have a 1"),
    'ands': ('AND', lambda a, b: a & b, "each result bit is 1 only where both inputs have a 1"),
    'orr': ('OR', lambda a, b: a | b, "each result bit is 1 where either input has a 1"),
    'eor': ('XOR', lambda a, b: a ^ b, "each result bit is 1 where exactly one input has a 1"),
}


def explain_logic(step):
    step.count(3, 4)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    first = step.operand(1, 'reg')
    bits = destination['bits']
    second, second_formula, _ = step.second_operand(2, bits)
    if second is None:
        raise Unexplained(f"This form of {step.mnemonic} isn't explained yet.")
    word, operation, meaning = LOGIC[step.mnemonic]
    a = step.read(first, 'before')
    expected = operation(a, second) & mask(bits)
    result = expected if destination['special'] == 'zr' else step.read(destination, 'after')
    if expected != result:
        raise Unexplained(TRACE_MISMATCH)
    if step.mnemonic == 'ands':
        check_flags(step, {'N': result >> (bits - 1), 'Z': int(result == 0), 'C': 0, 'V': 0})
    text = f"{name(destination)} = {name(first)} {word} {second_formula} (bitwise: {meaning})."
    if destination['special'] == 'zr':
        text += " The result is thrown away (xzr discards writes)."
    else:
        text += step.destination_notes(destination, result)
    if step.mnemonic == 'ands':
        text += explain_flags(step)
    return text


SHIFT_MEANINGS = {
    'lsl': ("left", "filling the bottom with 0s; same as multiplying by {factor} when nothing falls off the top"),
    'lsr': ("right", "filling the top with 0s; unsigned divide by {factor}, rounded down"),
    'asr': ("right", "copying the sign bit into the top; signed divide by {factor}, rounded down"),
}


def explain_shift(step):
    step.count(3)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    source = step.operand(1, 'reg')
    amount_operand = step.operand(2, 'reg', 'imm')
    bits = destination['bits']
    note = ''
    if amount_operand['kind'] == 'imm':
        if amount_operand['value'] is None:
            raise Unexplained(f"This form of {step.mnemonic} isn't explained yet.")
        amount = amount_operand['value']
        amount_text = f"{amount}"
        factor = 2 ** amount if amount <= 16 else f"2^{amount}"
    else:
        raw = step.read(amount_operand, 'before')
        amount = raw % bits
        amount_text = name(amount_operand)
        factor = f"2^{name(amount_operand)}"
        if raw >= bits:
            note = f" Only {name(amount_operand)} mod {bits} is used as the shift amount."
    value = step.read(source, 'before')
    result = step.read(destination, 'after')
    if shift_value(step.mnemonic, value, amount, bits) != result:
        raise Unexplained(TRACE_MISMATCH)
    direction, meaning = SHIFT_MEANINGS[step.mnemonic]
    unit = 'bit' if amount_text == '1' else 'bits'
    return (f"{name(destination)} = {name(source)} shifted {direction} by {amount_text} {unit} "
            f"({meaning.format(factor=factor)})."
            + note + step.destination_notes(destination, result))


# ---------- comparisons ----------

def unsigned_text(value):
    return str(value) if value < 2 ** 31 else hex(value)


def explain_compare(step, offset=0):
    step.count(2 + offset, 3 + offset)
    step.require_next_pc()
    first = step.operand(offset, 'reg')
    bits = first['bits']
    second, second_formula, second_shown = step.second_operand(offset + 1, bits)
    a = step.read(first, 'before')
    if second is not None:
        check_flags(step, subtraction_flags(a, second, bits))
    values = flags(step.after)
    text = (f"Compare {name(first)} with {second_formula}: compute {step.show(first, a)} − {second_shown} "
            f"and set the flags; the result is not saved. Flags: {flag_text(step.after)}.")
    if values['Z']:
        text += " The values are equal."
    else:
        signed_less = values['N'] != values['V']
        unsigned_lower = values['C'] == 0
        if second is None:
            signed_word = 'less than' if signed_less else 'greater than'
            unsigned_word = 'lower than' if unsigned_lower else 'higher than'
            text += (f" As signed numbers {name(first)} is {signed_word} {second_formula}; "
                     f"as unsigned numbers it is {unsigned_word}.")
        else:
            signed_relation = f"{signed(a, bits)} {'<' if signed_less else '>'} {signed(second, bits)}"
            unsigned_relation = f"{unsigned_text(a)} {'<' if unsigned_lower else '>'} {unsigned_text(second)}"
            if signed_less == unsigned_lower:
                text += f" {signed_relation}, whether read as signed or unsigned."
            else:
                text += f" Signed: {signed_relation}. Unsigned: {unsigned_relation}."
    return text + " Conditional branches such as beq or blt read these flags."


# ---------- branches and calls ----------

def condition_holds(condition, f):
    return {
        'eq': f['Z'] == 1, 'ne': f['Z'] == 0,
        'lt': f['N'] != f['V'], 'ge': f['N'] == f['V'],
        'gt': f['Z'] == 0 and f['N'] == f['V'], 'le': f['Z'] == 1 or f['N'] != f['V'],
        'lo': f['C'] == 0, 'hs': f['C'] == 1,
        'hi': f['C'] == 1 and f['Z'] == 0, 'ls': f['C'] == 0 or f['Z'] == 1,
    }[condition]


def condition_reason(condition, f, holds):
    n, z, c, v = f['N'], f['Z'], f['C'], f['V']
    if condition in ('eq', 'ne'):
        return f"Z is {z} (the compared values were {'equal' if z else 'not equal'})"
    if condition in ('lt', 'ge'):
        return f"N is {n} and V is {v} ({'N ≠ V: signed less than' if n != v else 'N = V: signed greater than or equal'})"
    if condition in ('gt', 'le'):
        greater = z == 0 and n == v
        return f"Z is {z}, N is {n}, V is {v} ({'signed greater than' if greater else 'signed less than or equal'})"
    if condition in ('lo', 'hs'):
        return f"C is {c} ({'unsigned lower' if c == 0 else 'unsigned higher or same'})"
    higher = c == 1 and z == 0
    return f"C is {c} and Z is {z} ({'unsigned higher' if higher else 'unsigned lower or same'})"


def branch_taken(step):
    return step.after[PC] != step.before[PC] + 4


# A branch to the very next instruction looks the same taken or not taken,
# so only a jump that happened without the condition is a mismatch
def check_branch(taken, holds):
    if taken and not holds:
        raise Unexplained(TRACE_MISMATCH)


def explain_branch(step):
    step.count(1)
    target = step.operand(0, 'label')['name']
    taken = branch_taken(step)
    if step.mnemonic == 'b':
        return f"Always jump to {target} ({hex(step.after[PC])}); b is an unconditional branch."
    condition = step.mnemonic[1:]
    current = flags(step.before)
    holds = condition_holds(condition, current)
    check_branch(taken, holds)
    reason = condition_reason(condition, current, holds)
    if holds:
        return f"Jump to {target} because {reason}."
    return f"Don't jump to {target} because {reason}; continue with the next instruction."


def explain_compare_branch(step):
    step.count(2)
    register = step.operand(0, 'reg')
    target = step.operand(1, 'label')['name']
    value = step.read(register, 'before')
    taken = branch_taken(step)
    jumps_on_zero = step.mnemonic == 'cbz'
    holds = (value == 0) == jumps_on_zero
    check_branch(taken, holds)
    shown = step.show(register, value)
    note = f" ({step.mnemonic} checks the register directly and doesn't use the flags.)"
    if holds:
        reason = f"{name(register)} is 0" if jumps_on_zero else f"{name(register)} is {shown}, not 0"
        return f"Jump to {target} because {reason}." + note
    reason = f"{name(register)} is {shown}, not 0" if jumps_on_zero else f"{name(register)} is 0"
    return f"Don't jump to {target} because {reason}; continue with the next instruction." + note


def explain_call(step):
    step.count(1)
    target = step.operand(0, 'label')['name']
    return_address = step.before[PC] + 4
    if step.after[30] != return_address:
        raise Unexplained(TRACE_MISMATCH)
    text = (f"Call {target}: save the return address {hex(return_address)} (the next instruction) in x30, "
            f"then jump to {target} ({hex(step.after[PC])}). Its ret will come back to {hex(return_address)}.")
    if step.before[30] not in (0, return_address):
        text += f" x30's old value {hex(step.before[30])} is overwritten, which is why functions save x30 on the stack."
    return text


def explain_return(step):
    step.count(0, 1)
    register = step.operand(0, 'reg') if step.operands else {'name': 'x30', 'number': 30, 'bits': 64, 'special': None}
    target = step.read(register, 'before')
    if step.after[PC] != target:
        raise Unexplained(TRACE_MISMATCH)
    if step.mnemonic == 'br':
        text = f"Jump to the address in {name(register)} ({hex(target)})."
        if register['number'] == 30:
            text += " Since x30 holds the return address, this returns to the caller like ret."
        return text
    return f"Return to the caller: jump to the return address in {name(register)} ({hex(target)})."


def explain_adr(step):
    step.count(2)
    step.require_next_pc()
    destination = step.operand(0, 'reg')
    label = step.operand(1, 'label')['name']
    result = step.read(destination, 'after')
    target = f"the page containing {label}" if step.mnemonic == 'adrp' else label
    return f"Put the address of {target} ({hex(result)}) into {name(destination)}."


# ---------- loads and stores ----------

def describe_offset(step, memory, bits):
    offset, index = memory['offset'], memory['index']
    if index is not None:
        index_value = step.read(index, 'before')
        if memory['shift'] is None:
            return index_value, name(index)
        amount = memory['shift']['amount']['value']
        if amount is None:
            raise Unexplained(f"This form of {step.mnemonic} isn't explained yet.")
        return (index_value << amount) & mask(64), f"{name(index)}×{2 ** amount}"
    if offset is None:
        return 0, None
    return offset['value'], offset['text']


def stack_note(step, address, size):
    if not STACK_START <= address < STACK_END:
        return ''
    if address < step.before[SP]:
        return " This address is below SP, outside the active stack."
    cells = [cell for cell in step.before_stack
             if cell['address'] < address + size and address < cell['address'] + cell['size']]
    if not cells or all(cell['value'] is None for cell in cells):
        return " Nothing was stored here yet, so this reads leftover memory."
    return ''


def explain_memory(step):
    step.count(2)
    step.require_next_pc()
    register = step.operand(0, 'reg')
    memory = step.operand(1, 'mem')
    is_load = step.mnemonic in LOAD_SIZES
    size = (LOAD_SIZES if is_load else STORE_SIZES)[step.mnemonic] or register['bits'] // 8
    base = memory['base']
    base_value = step.read(base, 'before')
    offset_value, offset_text = describe_offset(step, memory, 64)

    kind = 'read' if is_load else 'write'
    matches = [access for access in step.accesses if access['kind'] == kind]
    if len(matches) != 1 or matches[0]['size'] != size:
        raise Unexplained(TRACE_MISMATCH)
    address = matches[0]['address']
    if offset_value is not None:
        expected = base_value if memory['mode'] == 'post' else (base_value + offset_value) & mask(64)
        if expected != address:
            raise Unexplained(TRACE_MISMATCH)

    new_base = step.read(base, 'after')
    if memory['mode'] == 'pre' and new_base != address:
        raise Unexplained(TRACE_MISMATCH)
    if memory['mode'] == 'post' and offset_value is not None and new_base != (base_value + offset_value) & mask(64):
        raise Unexplained(TRACE_MISMATCH)

    where = "stack address" if STACK_START <= address < STACK_END else "address"
    detail = ''
    if memory['mode'] == 'offset' and offset_text is not None:
        if offset_text.startswith('-'):
            detail = f" ({name(base)} − {offset_text[1:]})"
        else:
            detail = f" ({name(base)} + {offset_text})"
    location = f"{where} {hex(address)}{detail}"

    if is_load:
        result = step.read(register, 'after')
        raw = result & mask(size * 8)
        body = f"load {plural(size)} from {location} into {name(register)}. {name(register)} = {step.show(register, result)}."
        if step.mnemonic in ('ldrb', 'ldrh'):
            body += f" The upper bits of {name(register)} are filled with 0s (zero extension)."
        elif step.mnemonic in ('ldrsb', 'ldrsh', 'ldrsw'):
            top_bit = raw >> (size * 8 - 1)
            body += (f" Sign extension copies the loaded value's top bit ({top_bit}) into the upper bits, "
                     f"so {hex(raw)} becomes {signed(result, register['bits'])}.")
        if register['special'] is None and step.read(register, 'before') == result:
            body += f" ({name(register)} already held this value.)"
        body += stack_note(step, address, size)
        if register['number'] == 30:
            body += " x30 holds the return address that ret uses."
    else:
        full = step.read(register, 'before')
        stored = full & mask(size * 8)
        if register['special'] == 'zr':
            value_text = f"0 ({register['name']})"
        elif size * 8 == register['bits']:
            value_text = f"{step.show(register, stored)} from {name(register)}"
        else:
            value_text = f"{stored} from {name(register)}"
        body = f"store {value_text} into {plural(size)} at {location}."
        if stored != full:
            lowest = "lowest byte is" if size == 1 else f"lowest {size} bytes are"
            body += f" {name(register)} is {step.show(register, full)}; only its {lowest} stored."
        if register['number'] == 30:
            body += " This saves the return address so a later ret can still find it."

    old_sp, new_sp = step.before[SP], step.after[SP]
    if base['special'] == 'sp' and memory['mode'] == 'pre' and not is_load and new_sp < old_sp:
        return (f"Push {name(register)} onto the stack (make room, then save it): SP moves down "
                f"{old_sp - new_sp} bytes ({hex(old_sp)} → {hex(new_sp)}), then " + body)
    if base['special'] == 'sp' and memory['mode'] == 'post' and is_load and new_sp > old_sp:
        return (f"Pop {name(register)} off the stack (read it back, then release the space): " + body
                + f" Then SP moves up {new_sp - old_sp} bytes ({hex(old_sp)} → {hex(new_sp)}).")
    if memory['mode'] == 'pre':
        return (f"Pre-index: first {name(base)} becomes {name(base)} + {offset_text} = {hex(new_base)}; then " + body)
    body = body[0].upper() + body[1:]
    if memory['mode'] == 'post':
        body += f" Then {name(base)} becomes {name(base)} + {offset_text} = {hex(new_base)} (post-index)."
    return body


HANDLERS = {
    'mov': explain_mov,
    'add': explain_add_sub, 'sub': explain_add_sub, 'adds': explain_add_sub, 'subs': explain_add_sub,
    'neg': explain_neg,
    'mul': explain_mul,
    'sdiv': explain_divide, 'udiv': explain_divide,
    'and': explain_logic, 'ands': explain_logic, 'orr': explain_logic, 'eor': explain_logic,
    'lsl': explain_shift, 'lsr': explain_shift, 'asr': explain_shift,
    'cmp': explain_compare,
    'b': explain_branch, **{mnemonic: explain_branch for mnemonic in BRANCH_CONDITIONS},
    'cbz': explain_compare_branch, 'cbnz': explain_compare_branch,
    'bl': explain_call, 'ret': explain_return, 'br': explain_return,
    'adr': explain_adr,
    'adrp': explain_adr,
    **{mnemonic: explain_memory for mnemonic in list(LOAD_SIZES) + list(STORE_SIZES)},
}


def explain_step(line, before, after, before_stack, accesses):
    parsed = parse_instruction(line)
    if parsed is None:
        return "This line is not an instruction, so there is nothing to explain."
    mnemonic, operands = parsed['mnemonic'], parsed['operands']
    handler = HANDLERS.get(mnemonic)
    if handler is None:
        return f"No explanation for {mnemonic}: it isn't one of the COS 217 instructions this panel covers."
    if operands is None:
        return f"This form of {mnemonic} isn't explained yet."
    try:
        return handler(Step(mnemonic, operands, before, after, before_stack, accesses))
    except Unexplained as error:
        return str(error)


def explain_heap_call(call, argument, result):
    if call == 'malloc':
        if result == 0:
            return f"malloc could not allocate {argument} bytes. It returns NULL in x0."
        return f"malloc allocates {argument} bytes at {result:#x} and returns the address in x0."
    if argument == 0:
        return "free(NULL) leaves the heap unchanged."
    return f"free releases the allocation at {argument:#x}."


# One explanation per snapshot: explanations[i] describes the instruction that
# turned snapshot i - 1 into snapshot i. explanations[0] is None.
def explain_trace(executed_statements, register_states, stack_states, memory_accesses, library_calls):
    explanations = [None]
    for i, statement in enumerate(executed_statements, start=1):
        before, after = register_states[i - 1:i + 1]
        call = library_calls.get(before[PC])
        if call:
            explanations.append(explain_heap_call(call, before[0], after[0]))
        else:
            explanations.append(explain_step(statement.text, before, after, stack_states[i - 1], memory_accesses[i]))
    return explanations
