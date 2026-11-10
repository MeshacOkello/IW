"""Assemble a sectioned ARM64 program with Keystone."""
import re
from dataclasses import dataclass

from keystone import KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, Ks, KsError

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
TOKENS = re.compile(r'''"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|/\*[\s\S]*?\*/|//[^\n]*|;''')
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
    pass


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
                raise AssemblyError(f'Line {statement.line}: duplicate label {label}')
            owners[label] = section
        if directive in SECTION_NAMES or directive == '.section':
            if directive != '.section' and operands:
                raise AssemblyError(f'Line {statement.line}: subsections are unsupported')
            if statement.labels:
                sections[section].append(Statement(statement.line, statement.labels, ''))
            section = operands.split(',', 1)[0].strip() if directive == '.section' else directive
            if section not in sections:
                raise AssemblyError(f'Line {statement.line}: unsupported section {section}')
            continue

        if directive in {'.equ', '.set', '.equiv'}:
            constants[section].append(statement.text)
        elif directive in METADATA:
            statement = Statement(statement.line, statement.labels, '')
        elif directive in ALIGN_DIRECTIVES or directive in RESERVE_DIRECTIVES:
            count = parse_number(operands.split(',', 1)[0])
            if count is None or not 0 <= count <= MAX_SECTION_SIZE:
                raise AssemblyError(f'Line {statement.line}: expected a bounded numeric size')
            if directive in {'.align', '.p2align'}:
                if count > 20:
                    raise AssemblyError(f'Line {statement.line}: alignment is too large')
                count = 1 << count
            reserved += count
            if reserved > MAX_SECTION_SIZE:
                raise AssemblyError(f'Line {statement.line}: total reservation is too large')
            if directive in ALIGN_DIRECTIVES and section != '.text':
                arguments = [argument.strip() for argument in operands.split(',')]
                if len(arguments) == 1:
                    arguments.append('0')
                elif not arguments[1]:
                    arguments[1] = '0'
                statement = Statement(statement.line, statement.labels, f'{directive} {", ".join(arguments)}')
        elif statement.is_instruction and section != '.text':
            raise AssemblyError(f'Line {statement.line}: instructions belong in .text')
        elif directive in DATA_DIRECTIVES and section == '.bss':
            raise AssemblyError(f'Line {statement.line}: use zero-filled storage in .bss')
        elif directive.startswith('.') and directive not in DATA_DIRECTIVES:
            if directive != '.ltorg' or section != '.text':
                raise AssemblyError(f'Line {statement.line}: unsupported directive {directive}')
        if statement.text or statement.labels:
            sections[section].append(statement)
    return sections, constants, owners


def assemble(assembler, lines, address, context):
    try:
        data, _ = assembler.asm('\n'.join(lines), addr=address, as_bytes=True)
    except (KsError, UnicodeEncodeError) as error:
        raise AssemblyError(f'{context}: {error}') from error
    if data is None:
        raise AssemblyError(f'{context}: Keystone could not assemble the source')
    return data


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
            raise AssemblyError(f'Line {statement.line}: {mnemonic} target is out of range or unaligned')
        # At address zero Keystone encodes these operands as displacements.
        text = f'{mnemonic} {register}, #{immediate}'
        address = 0
    else:
        text = LOW12.sub(f'#{target & (PAGE_SIZE - 1)}', statement.text)
        address = pc
    encoded = assemble(assembler, [text], address, f'Line {statement.line}')
    if len(encoded) != 4:
        raise AssemblyError(f'Line {statement.line}: expected a single instruction')
    return encoded


def assemble_section(assembler, name, address, statements, constants, externals, marker_prefix):
    if not statements:
        return b'', {}, {}, ()
    lines = definitions(externals) + constants
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
    output = assemble(assembler, lines, address, name)
    size = len(output) - 8 * len(markers)
    if not 0 <= size <= MAX_SECTION_SIZE:
        raise AssemblyError(f'{name}: invalid section size')

    values = {
        marker: int.from_bytes(output[offset:offset + 8], 'little')
        for offset, marker in zip(range(size, len(output), 8), markers)
    }
    code = bytearray(output[:size])
    instructions = {}
    for start, (statement, end, expression_marker, needs_encoding) in sites.items():
        pc, end = values[start], values[end]
        if pc % 4 or end - pc != 4 or not address <= pc < end <= address + size:
            raise AssemblyError(f'Line {statement.line}: expected one aligned ARM64 instruction')
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
        definition.split(None, 1)[1].split(',', 1)[0].strip()
        for group in constants.values() for definition in group
        if len(definition.split(None, 1)) == 2
    }
    library_symbols = {
        name: address for name, address in LIBRARY_SYMBOLS.items()
        if name not in owners and name not in constant_names
    }
    marker_prefix = '__simulator_location_'
    while marker_prefix in source:
        marker_prefix += '_'

    external_constants = {
        name: [definition for other in SECTION_NAMES if other != name for definition in constants[other]]
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
        raise AssemblyError('.text: section exceeds the space below the stack')
    symbols.update(labels)
    image = [Section('.text', TEXT_START, len(code), code)]

    for name, (address, size) in layouts.items():
        externals = {label: value for label, value in symbols.items() if owners[label] != name}
        data, labels, _, strings = assemble_section(assembler, name, address, sections[name], external_constants[name], library_symbols | externals, marker_prefix)
        if len(data) != size or any(symbols[label] != value for label, value in labels.items()):
            raise AssemblyError(f'{name}: section layout depends on a cross-section symbol')
        if name == '.bss':
            if any(data):
                raise AssemblyError('.bss: storage must be zero-filled')
            data = b''
        image.append(Section(name, address, size, data, strings))
    return Program(tuple(image), symbols, instructions, owners)
