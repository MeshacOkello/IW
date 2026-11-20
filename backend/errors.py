"""Structured, student-facing diagnostics for every way a run can fail.

Every failure the backend reports carries a `kind` so the frontend can say
what went wrong at the right altitude:

    request      the frontend sent something this endpoint cannot accept
    assembly     the program could not be turned into machine code
    unsupported  the program is valid AArch64 the simulator does not simulate
    runtime      the program assembled but failed while executing
    internal     a bug in the simulator itself

`assembly`, `unsupported` and `runtime` are the student's program; `request`
and `internal` are not, so they are never phrased as a mistake in the source.
"""
import difflib
import re

from keystone import KsError
import keystone as ks
from unicorn import UcError
import unicorn as uc

REQUEST = 'request'
ASSEMBLY = 'assembly'
UNSUPPORTED = 'unsupported'
RUNTIME = 'runtime'
INTERNAL = 'internal'

INTERNAL_MESSAGE = ('The simulator hit an internal error and stopped this run. '
                    'Your program was not the cause. The details were logged on the server.')

# Mnemonics the simulator covers, used only to suggest a correction for a
# misspelling. Keystone, not this list, decides what actually assembles.
KNOWN_MNEMONICS = (
    'add', 'adds', 'adr', 'adrp', 'and', 'ands', 'asr', 'b', 'beq', 'bne', 'blt', 'ble',
    'bgt', 'bge', 'blo', 'bls', 'bhi', 'bhs', 'bl', 'blr', 'br', 'cbnz', 'cbz', 'cmn',
    'cmp', 'csel', 'cset', 'eor', 'ldp', 'ldr', 'ldrb', 'ldrh', 'ldrsb', 'ldrsh', 'ldrsw',
    'ldur', 'lsl', 'lsr', 'madd', 'mov', 'movk', 'movn', 'movz', 'msub', 'mul', 'mvn',
    'neg', 'nop', 'orr', 'ret', 'sdiv', 'stp', 'str', 'strb', 'strh', 'stur', 'sub',
    'subs', 'sxtb', 'sxth', 'sxtw', 'tbnz', 'tbz', 'tst', 'udiv', 'uxtb', 'uxth',
)

# Keystone reports a failure for a whole section, so the text of the error is
# the only clue to what the student typed wrong.
KEYSTONE_CODES = {
    getattr(ks, name): name for name in dir(ks) if name.startswith('KS_ERR_')
}
UNICORN_CODES = {
    getattr(uc, name): name for name in dir(uc) if name.startswith('UC_ERR_')
}

MNEMONIC = re.compile(r'^(\.?[A-Za-z][\w.$]*)')


def render(parts):
    """Flatten message parts the way HeapError renders them, for plain text."""
    return ''.join(
        part if isinstance(part, str) else (
            hex(int(part['value'])) if part['kind'] == 'address' else part['value']
        )
        for part in parts
    )


def payload(kind, message, *, parts=None, line=None, source_line=None,
            detail=None, suggestion=None):
    """Build the error object the frontend renders. Absent fields are omitted."""
    error = {'kind': kind, 'message': message}
    if parts:
        error['message_parts'] = list(parts)
    if line is not None:
        error['line'] = line
    if source_line:
        error['source_line'] = source_line
    if detail:
        error['detail'] = detail
    if suggestion:
        error['suggestion'] = suggestion
    return error


def source_line_text(source, line):
    """The student's own text for a 1-based line number, trimmed for display."""
    if not isinstance(source, str) or not isinstance(line, int) or line < 1:
        return None
    lines = source.replace('\r\n', '\n').split('\n')
    if line > len(lines):
        return None
    return lines[line - 1].strip() or None


# Below this, a name is too short for a near-miss to mean anything: "l" is
# within one edit of bl, b and lsl alike, so offering any of them is a guess.
SHORTEST_CORRECTABLE = 3


def closest(word, candidates, cutoff=0.7):
    """The likeliest intended spelling of `word`, or None.

    Only a genuine near-miss earns a suggestion: the name has to be long
    enough for the resemblance to mean something, and within one character of
    the length of the candidate. A transposition is the most common typing
    slip and difflib does not favour it, so a candidate built from exactly the
    same letters wins over a merely similar one: "mvo" is far more likely to
    be "mov" than "mvn".
    """
    lowered = word.lower()
    if len(lowered) < SHORTEST_CORRECTABLE:
        return None
    # Compared without case, so "Siz" still finds the upper-case constant
    # "SIZE" that COS 217 style uses; the candidate comes back as written.
    spellings = {}
    for candidate in sorted(candidates):
        spellings.setdefault(candidate.lower(), candidate)
    matches = [
        match for match in difflib.get_close_matches(lowered, sorted(spellings), n=5, cutoff=cutoff)
        if abs(len(match) - len(lowered)) <= 1
    ]
    if not matches:
        return None
    letters = sorted(lowered)
    return spellings[next((match for match in matches if sorted(match) == letters), matches[0])]


def syntax_message(statement_text):
    """The one message for a line the assembler cannot make an instruction of.

    A failure to parse, bad operands, an operand the assembler cannot resolve
    and an encoding that produces nothing are all the same thing to a student
    reading their own line: the syntax is wrong. Naming the low-level reason
    would be guessing at which of them it was.
    """
    match = MNEMONIC.match(statement_text.strip()) if statement_text else None
    mnemonic = match[1].lower() if match else None
    if mnemonic and not mnemonic.startswith('.'):
        return f'Wrong syntax. AArch64 does not allow the operands of "{mnemonic}" in this form.'
    return 'Wrong syntax. This line is not a valid AArch64 instruction.'


REGISTER = re.compile(r'(?<![\w.$])([xw])(\d+)(?![\w.$])', re.ASCII | re.IGNORECASE)


def invalid_register(statement_text, defined_labels=()):
    """A register the line names that AArch64 does not have, if there is one.

    x0-x30 and w0-w30 are the general-purpose registers; x31 is not written as
    a number at all, it is spelled sp or xzr depending on the instruction.
    """
    body = statement_text.split(None, 1)
    operands = body[1] if len(body) == 2 else ''
    known = {label.lower() for label in defined_labels}
    for match in REGISTER.finditer(operands):
        digits = match[2]
        # A name the program defines is a label, whatever it looks like.
        if match[0].lower() in known:
            continue
        if int(digits) > 30 or (len(digits) > 1 and digits[0] == '0'):
            return match[0]
    return None


# Instructions whose register operands must all be the same width. The loads,
# stores and extends deliberately mix x and w, so they are not listed.
SAME_WIDTH_OPERANDS = {
    'mov', 'mvn', 'neg', 'negs', 'add', 'adds', 'sub', 'subs', 'cmp', 'cmn',
    'mul', 'madd', 'msub', 'mneg', 'sdiv', 'udiv', 'and', 'ands', 'orr', 'orn',
    'eor', 'eon', 'tst', 'bic', 'lsl', 'lsr', 'asr', 'ror', 'csel', 'csinc',
}
REGISTER_WIDTH = re.compile(r'(?<![\w.$])([xw])(?:\d+|zr)(?![\w.$])', re.ASCII | re.IGNORECASE)


def mismatched_register_widths(statement_text):
    """True when a line mixes x and w registers where both must match.

    Memory operands are left alone: "ldr w0, [x1]" is correct, since the
    address is always 64-bit while the value loaded need not be.
    """
    parts = statement_text.split(None, 1)
    if len(parts) != 2 or parts[0].lower() not in SAME_WIDTH_OPERANDS:
        return False
    operands = parts[1]
    if '[' in operands:
        return False
    widths = {match[1].lower() for match in REGISTER_WIDTH.finditer(operands)}
    return widths == {'x', 'w'}


def instruction_failure(statement_text, defined_labels=()):
    """Message and advice for a line the assembler could not encode.

    Keystone reports an operand it cannot resolve the same way as one that is
    malformed, so an undefined name is looked for here rather than trusted to
    the error code: "mov x2, n" is a missing "n", not bad syntax.
    """
    if not statement_text:
        return 'The assembler could not encode this section.', None
    register = invalid_register(statement_text, defined_labels)
    if register:
        return (f'"{register}" is not an AArch64 register.',
                'The general-purpose registers are x0 to x30, or w0 to w30 for their '
                '32-bit halves, plus sp and xzr.')
    if mismatched_register_widths(statement_text):
        return ('Mismatched register sizes.',
                'Use x registers for 64-bit values and w registers for their 32-bit '
                'halves, but not both in one instruction.')
    name = undefined_symbol(statement_text, defined_labels)
    if name:
        alternative = closest(name, defined_labels, cutoff=0.6)
        return (f'The label "{name}" is used here but never defined.',
                f'Did you mean "{alternative}"?' if alternative else None)
    return syntax_message(statement_text), None


def code_of(error, table):
    """The symbolic KS_/UC_ name for an exception's errno, when it has one."""
    return table.get(getattr(error, 'errno', None))


# --- assembly ---------------------------------------------------------------

def describe_keystone_error(error, statement_text=None, defined_labels=()):
    """Turn a Keystone failure into plain language plus a correction when sure."""
    code = code_of(error, KEYSTONE_CODES)
    mnemonic = None
    if statement_text:
        match = MNEMONIC.match(statement_text.strip())
        mnemonic = match[1].lower() if match else None
    # A directive that fails is never a bad instruction, whatever Keystone
    # calls the failure, so say so with the words the student can act on.
    directive = mnemonic if mnemonic and mnemonic.startswith('.') else None
    if directive in ('.equ', '.set', '.equiv'):
        return ('This constant definition could not be evaluated. A constant must be a '
                'number, or an expression over constants already defined above it, and '
                'may not refer to itself.', None, ASSEMBLY)
    if directive and code and 'MNEMONIC' in code:
        return (f'Wrong syntax. "{directive}" could not be assembled with these arguments.',
                None, ASSEMBLY)

    if code == 'KS_ERR_ASM_MNEMONICFAIL':
        subject = f'"{mnemonic}"' if mnemonic else 'This line'
        message = f'{subject} is not an AArch64 instruction.'
        suggestion = None
        if mnemonic:
            # A low cutoff so a transposition such as "mvo" still reaches
            # "mov"; the advice is phrased as a question either way.
            alternative = closest(mnemonic, KNOWN_MNEMONICS, cutoff=0.6)
            if alternative and alternative != mnemonic:
                suggestion = f'Did you mean "{alternative}"?'
        return message, suggestion, ASSEMBLY

    if code == 'KS_ERR_ASM_SYMBOL_MISSING':
        name = undefined_symbol(statement_text, defined_labels)
        if not name:
            return 'This line refers to a label that is never defined.', None, ASSEMBLY
        message, suggestion = instruction_failure(statement_text, defined_labels)
        return message, suggestion, ASSEMBLY

    if code == 'KS_ERR_ASM_INVALIDOPERAND':
        return (*instruction_failure(statement_text, defined_labels), ASSEMBLY)

    if code == 'KS_ERR_ASM_SYMBOL_REDEFINED':
        return 'This label is defined more than once.', None, ASSEMBLY

    if code in ('KS_ERR_ASM_DIRECTIVE_UNKNOWN', 'KS_ERR_ASM_DIRECTIVE_INVALID',
                'KS_ERR_ASM_DIRECTIVE_TOKEN', 'KS_ERR_ASM_DIRECTIVE_ID',
                'KS_ERR_ASM_DIRECTIVE_COMMA', 'KS_ERR_ASM_DIRECTIVE_STR'):
        return 'Wrong syntax. This assembler directive is not valid here.', None, ASSEMBLY

    if code == 'KS_ERR_ASM_DIRECTIVE_VALUE_RANGE':
        return ('A value in this directive is outside the range its size allows.',
                'Use a wider directive, such as .word or .quad.', ASSEMBLY)

    if code == 'KS_ERR_ASM_DIRECTIVE_EQU':
        return ('This constant definition could not be evaluated. A constant must be a '
                'number, or an expression over constants already defined above it, and '
                'may not refer to itself.', None, ASSEMBLY)

    if code in ('KS_ERR_ASM_ESC_SEQUENCE', 'KS_ERR_ASM_ESC_BACKSLASH',
                'KS_ERR_ASM_ESC_OCTAL', 'KS_ERR_ASM_ESC_STR'):
        return ('A string on this line contains an escape the assembler does not accept.',
                r'Use \n, \t, \\ or \" inside strings.', ASSEMBLY)

    if code in ('KS_ERR_ASM_EXPR_TOKEN', 'KS_ERR_ASM_EXPR_BRACKET',
                'KS_ERR_ASM_RPAREN', 'KS_ERR_ASM_TOKEN_INVALID',
                'KS_ERR_ASM_STAT_TOKEN'):
        return (*instruction_failure(statement_text, defined_labels), ASSEMBLY)

    if code in ('KS_ERR_ASM_INSN_UNSUPPORTED', 'KS_ERR_ASM_UNSUPPORTED',
                'KS_ERR_ASM_MISSINGFEATURE', 'KS_ERR_ASM_ARCH',
                'KS_ERR_ASM_VARIANT_INVALID'):
        return ('This instruction is not available in the AArch64 subset the simulator assembles.',
                None, UNSUPPORTED)

    if code in ('KS_ERR_ASM_MACRO_INVALID', 'KS_ERR_ASM_MACRO_ARGS', 'KS_ERR_ASM_MACRO_EQU',
                'KS_ERR_ASM_MACRO_LEVELS_EXCEED', 'KS_ERR_ASM_MACRO_PAREN',
                'KS_ERR_ASM_MACRO_STR', 'KS_ERR_ASM_MACRO_TOKEN'):
        return 'Assembler macros are not supported.', None, UNSUPPORTED

    # An unmapped Keystone code. What is certain is that the line is wrong, so
    # report it at the same level as every other syntax failure.
    return (*instruction_failure(statement_text, defined_labels), ASSEMBLY)


def undefined_symbol(statement_text, defined_labels):
    """Guess which name in a line is the undefined one."""
    if not statement_text:
        return None
    body = statement_text.split(None, 1)
    operands = body[1] if len(body) == 2 else ''
    known = {label.lower() for label in defined_labels}
    for name in re.findall(r'[A-Za-z_.$][\w.$]*', operands):
        lowered = name.lower()
        # Registers, condition codes and shifts are not labels.
        if re.fullmatch(r'[xw]\d+|[xw]zr|sp|wsp|lr|pc', lowered):
            continue
        if lowered in ('lsl', 'lsr', 'asr', 'ror', 'uxtb', 'uxth', 'uxtw',
                       'sxtb', 'sxth', 'sxtw', 'uxtx', 'sxtx', 'msl'):
            continue
        if lowered in ('eq', 'ne', 'cs', 'hs', 'cc', 'lo', 'mi', 'pl', 'vs', 'vc',
                       'hi', 'ls', 'ge', 'lt', 'gt', 'le', 'al', 'nv'):
            continue
        if lowered in known:
            continue
        return name
    return None


def assembly_error(message, *, line=None, source=None, suggestion=None,
                   detail=None, kind=ASSEMBLY):
    return payload(
        kind, message, line=line, suggestion=suggestion, detail=detail,
        source_line=source_line_text(source, line) if source is not None else None,
    )


# --- runtime ----------------------------------------------------------------

# Where an address lands, for an explanation that names the region.
def region_name(address, regions):
    for start, end, name in regions:
        if start <= address < end:
            return name
    return None


def describe_unicorn_error(error, fault, regions):
    """Explain a CPU fault, naming the faulting address when Unicorn reported one."""
    code = code_of(error, UNICORN_CODES) or ''
    address = fault.get('address') if fault else None
    size = fault.get('size') if fault else None
    parts = None
    suggestion = None

    # Addresses go through message_parts so the frontend can honour the
    # student's hex/decimal preference; `render` also gives the plain string.
    def at_address(opening, closing, *, with_size=True):
        if address is None:
            return opening.replace(' {size} bytes', '').rstrip() + '.', None
        pieces = []
        if with_size and size:
            before, _, after = opening.partition('{size}')
            pieces += [before, {'kind': 'data', 'value': str(size)}, after]
        else:
            pieces.append(opening.replace(' {size} bytes', ''))
        pieces += [{'kind': 'address', 'value': str(address)}, closing]
        return render(pieces), pieces

    if code in ('UC_ERR_READ_UNMAPPED', 'UC_ERR_WRITE_UNMAPPED'):
        action = 'read' if code == 'UC_ERR_READ_UNMAPPED' else 'wrote'
        message, parts = at_address(
            f'This instruction {action} {{size}} bytes at ',
            ', which is not memory the program owns.',
        )
        suggestion = unmapped_suggestion(address, regions, action)
    elif code == 'UC_ERR_WRITE_PROT':
        message, parts = at_address(
            'This instruction tried to write {size} bytes at ', ', which is read-only memory.')
        where = region_name(address, regions) if address is not None else None
        suggestion = (f'{where} is read-only. Move the data you want to change into .data or .bss.'
                      if where else 'Move data you need to change into .data or .bss.')
    elif code == 'UC_ERR_READ_PROT':
        message, parts = at_address(
            'This instruction tried to read {size} bytes at ', ', which is not readable.')
    elif code in ('UC_ERR_FETCH_UNMAPPED', 'UC_ERR_FETCH_PROT'):
        message, parts = at_address(
            'The program tried to execute the address ',
            ', which does not hold any of its instructions.', with_size=False)
        suggestion = ('A function that falls off its end without "ret", or a branch through a '
                      'register holding the wrong value, lands here.')
    elif code in ('UC_ERR_READ_UNALIGNED', 'UC_ERR_WRITE_UNALIGNED', 'UC_ERR_FETCH_UNALIGNED'):
        message, parts = at_address('This instruction accessed {size} bytes at ',
                                    ', which is not aligned for that access.')
        suggestion = None
    elif code == 'UC_ERR_INSN_INVALID':
        message = ('The CPU could not decode the instruction at this line. The simulator '
                   'executes a subset of AArch64, and this encoding is outside it.')
    elif code == 'UC_ERR_EXCEPTION':
        message = ('This instruction raised a CPU exception the simulator does not handle. '
                   'Instructions that trap to an operating system, such as "svc" or "brk", '
                   'have no effect here.')
    else:
        message = 'The CPU stopped on this instruction.'

    return message, parts, suggestion, code or str(error)


def unmapped_suggestion(address, regions, action):
    if address is None:
        return None
    if address == 0:
        return f'The address is 0, so the program {action} through a null pointer.'
    if address < 0x1000:
        return ('The address is very small, so the register used as the pointer probably held a '
                'small integer rather than an address.')
    stack = next(((start, end) for start, end, name in regions if name == 'the stack'), None)
    if stack and address < stack[0] and stack[0] - address < 0x4000:
        return ('The address is just below the stack, so the program may have pushed more than '
                'the simulated 4 KiB stack holds.')
    return None


# Advice for the problems the heap and the library calls detect themselves.
# Keyed by the opening of the message those modules raise.
HEAP_SUGGESTIONS = (
    ('double free',
     'Each allocation is freed once. Set the pointer to NULL after freeing it so a '
     'second free is harmless.'),
    ('invalid free',
     'Pass free the exact pointer malloc returned, not one that has moved through '
     'arithmetic.'),
    ('out-of-bounds heap access',
     'The access runs past the end of the allocation. Check the index against the '
     'size passed to malloc.'),
    ('use-after-free',
     'This block was already freed. A pointer must not be used after the memory '
     'behind it is released.'),
    ('write into read-only memory',
     'Move the data you want to change into .data or .bss.'),
    ('unterminated string',
     'A C string ends with a 0 byte. Use .asciz rather than .ascii, and make sure '
     'the pointer reaches the terminator.'),
    ('invalid',
     'The register used as the pointer does not hold an address the program owns. '
     'Check how it was computed.'),
)


def heap_suggestion(message):
    for prefix, advice in HEAP_SUGGESTIONS:
        if message.startswith(prefix):
            return advice
    return None


def runtime_error(message, *, parts=None, line=None, source=None, suggestion=None,
                  detail=None, kind=RUNTIME):
    return payload(
        kind, message, parts=parts, line=line, suggestion=suggestion, detail=detail,
        source_line=source_line_text(source, line) if source is not None else None,
    )


def legacy_text(error):
    """The flat `error` string, kept so existing clients keep working."""
    prefix = f"Line {error['line']}: " if error.get('line') is not None else ''
    return prefix + error['message']


def legacy_parts(error):
    """The flat `error_parts` list, or None when the message has no numbers."""
    parts = error.get('message_parts')
    if not parts:
        return None
    prefix = f"Line {error['line']}: " if error.get('line') is not None else ''
    return ([prefix] if prefix else []) + list(parts)


__all__ = [
    'ASSEMBLY', 'INTERNAL', 'INTERNAL_MESSAGE', 'REQUEST', 'RUNTIME', 'UNSUPPORTED',
    'KsError', 'UcError', 'assembly_error', 'closest', 'describe_keystone_error',
    'describe_unicorn_error', 'heap_suggestion', 'instruction_failure',
    'invalid_register', 'mismatched_register_widths',
    'legacy_parts', 'legacy_text',
    'syntax_message',
    'payload', 'region_name',
    'render', 'runtime_error', 'source_line_text', 'undefined_symbol',
]
