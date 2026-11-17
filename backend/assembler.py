"""Assemble a sectioned ARM64 program with Keystone."""
import difflib
import re
from dataclasses import dataclass

from keystone import KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, Ks, KsError

from errors import ASSEMBLY, UNSUPPORTED, describe_keystone_error
from heap import LIBRARY_SYMBOLS
from instruction_parser import parse_number

PAGE_SIZE = 0x1000
TEXT_START = 0x1000
STACK_START = 0x8000
STACK_END = 0x9000
SECTION_NAMES = ('.text', '.data', '.rodata', '.bss')
MAX_SECTION_SIZE = 1 << 20

NAME = r'[A-Za-z_.$][\w.$]*'
LABEL = re.compile(rf'^({NAME}):\s*', re.ASCII)
STRING = r'"(?:\\.|[^"\\\n])*"'
CHARACTER = r"'(?:\\.|[^'\\\n])*'"
BLOCK_COMMENT = r'/\*[\s\S]*?\*/'
LINE_COMMENT = r'//[^\n]*'
TOKENS = re.compile(f'{STRING}|{CHARACTER}|{BLOCK_COMMENT}|{LINE_COMMENT}|;')

# The same grammar, plus the openings that never closed. Keystone loops
# forever inside its lexer on an unterminated string literal, so those have
# to be rejected here, before any source reaches it.
UNCLOSED = re.compile(
    f'{STRING}|{CHARACTER}|{BLOCK_COMMENT}|{LINE_COMMENT}'
    r'|(?P<hash>^[ \t]*\#[^\n]*)'
    r'|(?P<string>")|(?P<character>\')|(?P<comment>/\*)|(?P<newline>\n)',
    re.MULTILINE,
)
ADDRESS_INSTRUCTION = re.compile(r'^(adrp?)\s+([^,]+),\s*(.+)$', re.IGNORECASE)
LOW12 = re.compile(rf'#?:lo12:({NAME}(?:\s*[+-]\s*(?:0[xX][0-9a-fA-F]+|\d+))?)', re.ASCII)

DATA_DIRECTIVES = {
    '.ascii', '.asciz', '.string', '.byte', '.hword', '.short', '.2byte',
    '.word', '.long', '.4byte', '.quad', '.xword', '.8byte', '.float', '.double',
}
STRING_DIRECTIVES = {'.ascii', '.asciz', '.string'}
RESERVE_DIRECTIVES = {'.space', '.skip', '.zero'}
ALIGN_DIRECTIVES = {'.align', '.p2align', '.balign'}
METADATA = {'.global', '.globl', '.type', '.size', '.local', '.hidden', '.extern'}


class AssemblyError(ValueError):
    """A program that cannot be assembled.

    `line` is the student's line number when it is known, and `kind` separates
    an outright mistake from valid assembly the simulator does not support.
    """

    def __init__(self, message, *, line=None, context=None, kind=None,
                 suggestion=None, detail=None):
        # `message` is the bare sentence; str() prefixes the location so the
        # text clients already display is unchanged.
        location = f'Line {line}' if line is not None else context
        super().__init__(f'{location}: {message}' if location else message)
        self.message = message
        self.line = line
        self.context = context
        self.kind = kind
        self.suggestion = suggestion
        self.detail = detail


@dataclass(frozen=True)
class Statement:
    line: int
    labels: tuple[str, ...]
    text: str

    @property
    def is_instruction(self):
        return bool(self.text) and not self.text.startswith('.')


@dataclass(frozen=True)
class Section:
    name: str
    address: int
    size: int
    data: bytes
    # Address ranges the string directives produced, so text can be shown as text.
    strings: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True)
class Program:
    sections: tuple[Section, ...]
    symbols: dict[str, int]
    instructions: dict[int, Statement]
    # The section each label was defined in.
    owners: dict[str, str]


def page_size(size):
    return (size + PAGE_SIZE - 1) // PAGE_SIZE * PAGE_SIZE


def directive_suggestion(directive):
    if directive in ('.section',):
        return None
    if directive in ('.text', '.data', '.bss', '.rodata'):
        return None
    closest_data = difflib.get_close_matches(
        directive, sorted(DATA_DIRECTIVES | RESERVE_DIRECTIVES | ALIGN_DIRECTIVES | METADATA),
        n=1, cutoff=0.7)
    return f'Did you mean "{closest_data[0]}"?' if closest_data else None


def check_literals(source):
    """Reject an unterminated string or block comment, naming its line.

    Keystone's lexer never returns on an unterminated double-quoted string, so
    this check is what keeps a single missing quote from wedging the backend.
    """
    line = 1
    for match in UNCLOSED.finditer(source.replace('\r\n', '\n')):
        if match['newline']:
            line += 1
            continue
        if match['hash']:
            continue
        if match['string']:
            raise AssemblyError(
                'This line opens a string with " that is never closed.', line=line,
                suggestion='Add the closing quote. A string cannot span lines.')
        if match['character']:
            raise AssemblyError(
                "This line opens a character literal with ' that is never closed.",
                line=line,
                suggestion="Add the closing quote, as in 'a'. A character literal "
                           'cannot span lines.')
        if match['comment']:
            raise AssemblyError(
                'This line opens a /* comment that is never closed.', line=line,
                suggestion='Close it with */, or use // for a comment that ends at the line.')
        line += match[0].count('\n')


def directive_arguments(operands):
    """Split a directive's operands on the commas that separate arguments.

    Commas inside a quoted string belong to the string, so ".asciz \"a,,b\""
    is one argument rather than three.
    """
    arguments = []
    current = ''
    quote = None
    characters = iter(operands)
    for character in characters:
        if quote:
            current += character
            if character == '\\':
                current += next(characters, '')
            elif character == quote:
                quote = None
        elif character in '"\'':
            quote = character
            current += character
        elif character == ',':
            arguments.append(current)
            current = ''
        else:
            current += character
    arguments.append(current)
    return [] if len(arguments) == 1 and not arguments[0].strip() else arguments


def check_directive_arguments(statement):
    """Reject a directive argument list with a hole in it.

    Keystone's parser never returns on a directive whose argument list has an
    empty entry, as in ".word 1, ,", ".word ,1" or ".equ A, 1,", so these are
    stopped here rather than assembled.
    """
    text = statement.text
    if not text.startswith('.'):
        return
    parts = text.split(None, 1)
    arguments = directive_arguments(parts[1]) if len(parts) == 2 else []
    if any(not argument.strip() for argument in arguments):
        raise AssemblyError(
            f'Wrong syntax. "{parts[0].lower()}" has an empty argument.', line=statement.line,
            suggestion='Remove the extra comma, or put a value between the commas.')


def source_statements(source):
    def replace_token(match):
        token = match[0]
        if token.startswith(('//', '/*')):
            return ' ' + '\n' * token.count('\n')
        if token == ';':
            return '\v'
        # The Keystone Python binding accepts ASCII. Encode UTF-8 string
        # bytes as assembler escapes while leaving existing escapes intact.
        if token.startswith('"'):
            return ''.join(char if char.isascii() else ''.join(
                f'\\{byte:03o}' for byte in char.encode('utf-8')) for char in token)
        return token

    source = TOKENS.sub(replace_token, source.replace('\r\n', '\n'))
    for line, text in enumerate(source.split('\n'), 1):
        if text.lstrip().startswith('#'):
            continue
        for text in text.split('\v'):
            text = text.strip()
            if not text:
                continue
            labels = []
            while match := LABEL.match(text):
                labels.append(match[1])
                text = text[match.end():].strip()
            yield Statement(line, tuple(labels), text)


def split_sections(source):
    check_literals(source)
    sections = {name: [] for name in SECTION_NAMES}
    constants = {name: [] for name in SECTION_NAMES}
    owners = {}
    section = '.text'
    reserved = 0
    for statement in source_statements(source):
        parts = statement.text.split(None, 1)
        directive = parts[0].lower() if parts else ''
        operands = parts[1] if len(parts) == 2 else ''
        for label in statement.labels:
            if label in owners:
                raise AssemblyError(
                    f'The label "{label}" is defined more than once.', line=statement.line)
            owners[label] = section
        if directive in SECTION_NAMES or directive == '.section':
            if directive != '.section' and operands:
                raise AssemblyError(
                    'Subsections are unsupported.', line=statement.line, kind=UNSUPPORTED,
                    suggestion=f'Write "{directive}" on its own, with no number after it.')
            if statement.labels:
                sections[section].append(Statement(statement.line, statement.labels, ''))
            section = operands.split(',', 1)[0].strip() if directive == '.section' else directive
            if section not in sections:
                raise AssemblyError(
                    f'"{section}" is not a section the simulator provides.', line=statement.line,
                    kind=UNSUPPORTED,
                    suggestion='Use .text for code, .data or .bss for writable data, '
                               'and .rodata for constants.')
            continue

        if directive in {'.equ', '.set', '.equiv'}:
            constants[section].append(statement)
        elif directive in METADATA:
            statement = Statement(statement.line, statement.labels, '')
        elif directive in ALIGN_DIRECTIVES or directive in RESERVE_DIRECTIVES:
            count = parse_number(operands.split(',', 1)[0])
            if count is None or not 0 <= count <= MAX_SECTION_SIZE:
                raise AssemblyError(
                    f'"{directive}" needs a size that is a number from 0 to {MAX_SECTION_SIZE}.',
                    line=statement.line)
            if directive in {'.align', '.p2align'}:
                if count > 20:
                    raise AssemblyError(
                        f'"{directive} {count}" asks for an alignment of 2^{count} bytes, which is too large.',
                        line=statement.line,
                        suggestion='".align 3" aligns to 8 bytes; the argument is a power of two, '
                                   'not a byte count.')
                count = 1 << count
            reserved += count
            if reserved > MAX_SECTION_SIZE:
                raise AssemblyError(
                    f'The program reserves more than {MAX_SECTION_SIZE} bytes in total.',
                    line=statement.line)
            if directive in ALIGN_DIRECTIVES and section != '.text':
                arguments = [argument.strip() for argument in operands.split(',')]
                if len(arguments) == 1:
                    arguments.append('0')
                elif not arguments[1]:
                    arguments[1] = '0'
                statement = Statement(statement.line, statement.labels, f'{directive} {", ".join(arguments)}')
        elif statement.is_instruction and section != '.text':
            raise AssemblyError(
                f'Instructions belong in .text, but this one is in {section}.', line=statement.line,
                suggestion='Add a ".text" line before the instruction, or move it above the '
                           'data section.')
        elif directive in DATA_DIRECTIVES and section == '.bss':
            raise AssemblyError(
                f'"{directive}" stores a value, but .bss only reserves zeroed space.',
                line=statement.line,
                suggestion='Use ".space N" in .bss, or move this directive to .data.')
        elif directive.startswith('.') and directive not in DATA_DIRECTIVES:
            if directive != '.ltorg' or section != '.text':
                raise AssemblyError(
                    f'"{directive}" is not a directive the simulator supports.',
                    line=statement.line, kind=UNSUPPORTED,
                    suggestion=directive_suggestion(directive))
        check_directive_arguments(statement)
        if statement.text or statement.labels:
            sections[section].append(statement)
    return sections, constants, owners


class NoMachineCode(Exception):
    """Keystone returned no bytes without reporting an error."""


@dataclass(frozen=True)
class Probe:
    """What a failed section needs in order to re-assemble one line at a time."""
    external_lines: tuple[str, ...]
    constants: tuple[Statement, ...]
    statements: tuple[Statement, ...]
    labels: tuple[str, ...]


def keystone_error(error, *, statement=None, context=None, defined_labels=()):
    """An AssemblyError that explains a Keystone failure in plain language."""
    if isinstance(error, NoMachineCode):
        return AssemblyError(
            'The assembler produced no machine code for this line.',
            line=statement.line if statement else None, context=context, detail='no output')
    if isinstance(error, UnicodeEncodeError):
        return AssemblyError(
            'This line contains a character the assembler cannot encode. Non-ASCII '
            'characters are only allowed inside quoted strings.',
            line=statement.line if statement else None, context=context)
    text = statement.text if statement else None
    message, suggestion, kind = describe_keystone_error(error, text, defined_labels)
    return AssemblyError(
        message, line=statement.line if statement else None,
        context=None if statement else context, kind=kind,
        suggestion=suggestion, detail=str(error),
    )


def probe_text(statement):
    """The text the section pass actually hands Keystone for one statement.

    adr/adrp operands and :lo12: expressions are rewritten before assembly, so
    a probe has to rewrite them the same way to reproduce a real failure.
    """
    if ADDRESS_INSTRUCTION.fullmatch(statement.text):
        return None  # assembled separately, from a computed displacement
    return LOW12.sub('#0', statement.text)


def locate_assembly_error(assembler, probe, address):
    """Find the statement Keystone choked on, by assembling each one alone.

    Keystone reports a failure for a whole section, which leaves a student with
    no line to look at. Re-assembling statement by statement against the same
    symbol preamble recovers the line for the common mistakes: an unknown
    mnemonic, bad operands, or a label that was never defined.
    """
    def attempt(lines):
        try:
            data, _ = assembler.asm('\n'.join(lines) or 'nop', addr=address, as_bytes=True)
        except (KsError, UnicodeEncodeError) as error:
            return error
        return None if data is not None else NoMachineCode()

    header = list(probe.external_lines) + [statement.text for statement in probe.constants]
    if attempt(header) is not None:
        # The symbol preamble itself is broken: blame the .equ responsible.
        for statement in probe.constants:
            error = attempt(list(probe.external_lines) + [statement.text])
            if error is not None:
                return statement, error
        return None, None

    # Labels defined in this section are absent from the preamble, so stand
    # them in as constants: a reference to a real label then resolves, and only
    # a genuinely undefined name still fails.
    base = header + [f'.equ {label}, 0' for label in probe.labels]
    for statement in probe.statements:
        text = probe_text(statement)
        if text is None:
            continue
        error = attempt(base + [text])
        if error is not None:
            return statement, error
    return None, None


def assemble(assembler, lines, address, context, *, probe=None, statement=None):
    try:
        data, _ = assembler.asm('\n'.join(lines), addr=address, as_bytes=True)
    except (KsError, UnicodeEncodeError) as error:
        failure = error
    else:
        if data is not None:
            return data
        failure = NoMachineCode()

    labels = probe.labels if probe else ()
    if probe is not None and statement is None:
        located, error = locate_assembly_error(assembler, probe, address)
        if located is not None:
            raise keystone_error(error or failure, statement=located,
                                 defined_labels=labels) from failure
    raise keystone_error(failure, statement=statement, context=context,
                         defined_labels=labels) from failure


def definitions(symbols):
    return [f'.equ {name}, {address}' for name, address in symbols.items()]


def encode_address_instruction(assembler, statement, pc, target):
    address_instruction = ADDRESS_INSTRUCTION.fullmatch(statement.text)
    if address_instruction:
        mnemonic, register, operand = address_instruction.groups()
        mnemonic = mnemonic.lower()
        immediate = parse_number(operand)
        if immediate is None:
            if operand.startswith('#'):
                immediate = target
            elif mnemonic == 'adrp':
                immediate = (target & -PAGE_SIZE) - (pc & -PAGE_SIZE)
            else:
                immediate = target - pc
        scale = PAGE_SIZE if mnemonic == 'adrp' else 1
        if immediate % scale or not -(1 << 20) <= immediate // scale < (1 << 20):
            raise AssemblyError(
                f'The target of "{mnemonic}" is out of range or unaligned.', line=statement.line,
                suggestion='adr reaches +/-1 MiB and adrp reaches whole 4 KiB pages; '
                           'use "adrp" with ":lo12:" for distant labels.')
        # At address zero Keystone encodes these operands as displacements.
        text = f'{mnemonic} {register}, #{immediate}'
        address = 0
    else:
        text = LOW12.sub(f'#{target & (PAGE_SIZE - 1)}', statement.text)
        address = pc
    encoded = assemble(assembler, [text], address, None, statement=statement)
    if len(encoded) != 4:
        raise AssemblyError(
            'This line assembled to more than one instruction.', line=statement.line,
            suggestion='Write one instruction per line.')
    return encoded


def assemble_section(assembler, name, address, statements, constants, externals, marker_prefix):
    if not statements:
        return b'', {}, {}, ()
    external_lines = definitions(externals)
    lines = external_lines + [constant.text for constant in constants]
    labels = []
    sites = {}
    markers = []
    strings = []
    for statement in statements:
        for label in statement.labels:
            lines.append(label + ':')
            labels.append(label)
            markers.append(label)
        if not statement.is_instruction:
            if statement.text:
                # Bracket string data so its bytes can be displayed as text.
                if statement.text.split(None, 1)[0].lower() in STRING_DIRECTIVES:
                    start = f'{marker_prefix}string{len(strings)}'
                    end = f'{start}_end'
                    lines.extend((start + ':', statement.text, end + ':'))
                    markers.extend((start, end))
                    strings.append((start, end))
                else:
                    lines.append(statement.text)
            continue

        start = f'{marker_prefix}{len(sites)}'
        end = f'{start}_end'
        expression_marker = None
        text = statement.text
        address_instruction = ADDRESS_INSTRUCTION.fullmatch(text)
        low12 = LOW12.search(text)
        if address_instruction:
            operand = address_instruction[3]
            expression = operand.lstrip('#') if parse_number(operand) is None else None
            text = 'nop'
        elif low12:
            expression = low12[1]
            text = LOW12.sub('#0', text)
        else:
            expression = None
        lines.append(start + ':')
        if expression is not None:
            expression_marker = f'{start}_target'
            lines.append(f'.equ {expression_marker}, {expression}')
            markers.append(expression_marker)
        lines.extend((text, end + ':'))
        markers.extend((start, end))
        sites[start] = (statement, end, expression_marker, bool(address_instruction or low12))

    # Drain literal pools before appending the address table so the table is
    # always at the end. It is stripped before loading the section into Unicorn.
    lines.append('.ltorg')
    lines.extend(f'.quad {marker}' for marker in markers)
    probe = Probe(tuple(external_lines), tuple(constants), tuple(statements), tuple(labels))
    output = assemble(assembler, lines, address, name, probe=probe)
    size = len(output) - 8 * len(markers)
    if not 0 <= size <= MAX_SECTION_SIZE:
        raise AssemblyError('The assembled contents of this section are not a valid size.',
                            context=name, detail='invalid section size')

    values = {
        marker: int.from_bytes(output[offset:offset + 8], 'little')
        for offset, marker in zip(range(size, len(output), 8), markers)
    }
    code = bytearray(output[:size])
    instructions = {}
    for start, (statement, end, expression_marker, needs_encoding) in sites.items():
        pc, end = values[start], values[end]
        if pc % 4 or end - pc != 4 or not address <= pc < end <= address + size:
            raise AssemblyError(
                'This line did not assemble to one aligned AArch64 instruction.',
                line=statement.line, suggestion='Write one instruction per line.')
        instructions[pc] = statement
        if needs_encoding:
            target = values.get(expression_marker)
            if target is not None and target >= 1 << 63:
                target -= 1 << 64
            code[pc - address:end - address] = encode_address_instruction(assembler, statement, pc, target)
    return (
        bytes(code),
        {label: values[label] for label in labels},
        instructions,
        tuple((values[start], values[end]) for start, end in strings),
    )


def assemble_program(source):
    sections, constants, owners = split_sections(source)
    assembler = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    constant_names = {
        statement.text.split(None, 1)[1].split(',', 1)[0].strip()
        for group in constants.values() for statement in group
        if len(statement.text.split(None, 1)) == 2
    }
    library_symbols = {
        name: address for name, address in LIBRARY_SYMBOLS.items()
        if name not in owners and name not in constant_names
    }
    marker_prefix = '__simulator_location_'
    while marker_prefix in source:
        marker_prefix += '_'

    external_constants = {
        name: [statement for other in SECTION_NAMES if other != name for statement in constants[other]]
        for name in SECTION_NAMES
    }

    # Size non-code sections first, with temporary addresses for symbols from
    # other sections. The final pass reassembles their contents with real symbols.
    layouts = {}
    symbols = {}
    address = STACK_END
    for name in SECTION_NAMES[1:]:
        externals = {label: 0 for label, owner in owners.items() if owner != name}
        data, labels, _, _ = assemble_section(assembler, name, address, sections[name], external_constants[name], library_symbols | externals, marker_prefix)
        layouts[name] = address, len(data)
        symbols.update(labels)
        address += page_size(max(len(data), 1))

    code, labels, instructions, _ = assemble_section(
        assembler, '.text', TEXT_START, sections['.text'], external_constants['.text'], library_symbols | symbols, marker_prefix,
    )
    if TEXT_START + len(code) > STACK_START:
        raise AssemblyError(
            f'The program has more code than the {STACK_START - TEXT_START} bytes '
            'the simulator reserves for instructions.', context='.text')
    symbols.update(labels)
    image = [Section('.text', TEXT_START, len(code), code)]

    for name, (address, size) in layouts.items():
        externals = {label: value for label, value in symbols.items() if owners[label] != name}
        data, labels, _, strings = assemble_section(assembler, name, address, sections[name], external_constants[name], library_symbols | externals, marker_prefix)
        if len(data) != size or any(symbols[label] != value for label, value in labels.items()):
            raise AssemblyError(
                'The size of this section depends on a label defined in another section.',
                context=name,
                suggestion='Use a numeric size for the storage this section reserves.')
        if name == '.bss':
            if any(data):
                raise AssemblyError('Storage in .bss must be zero-filled.', context='.bss',
                                suggestion='Reserve space with ".space N", or move initialised '
                                           'data to .data.')
            data = b''
        image.append(Section(name, address, size, data, strings))
    return Program(tuple(image), symbols, instructions, owners)
