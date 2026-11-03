import re

# Turns one line of assembly text into a mnemonic and a list of operands.
# Operands are dicts with a 'kind':
#   reg   {'name', 'number', 'bits', 'special'}  special is 'sp', 'zr' or None
#   imm   {'text', 'value'}                       value is None for symbols like N-1
#   label {'name'}                                 a bare word (branch target, symbol)
#   shift {'op', 'amount'}                         e.g. "lsl 2" after a register
#   mem   {'base', 'offset', 'index', 'shift', 'mode', 'text'}
#         mode is 'offset', 'pre' ([xn, 8]!) or 'post' ([xn], 8)

# Dotted and alternate branch spellings, mapped to the COS 217 spelling
BRANCH_ALIASES = {
    'b.eq': 'beq', 'b.ne': 'bne', 'b.lt': 'blt', 'b.le': 'ble', 'b.gt': 'bgt', 'b.ge': 'bge',
    'b.lo': 'blo', 'b.ls': 'bls', 'b.hi': 'bhi', 'b.hs': 'bhs',
    'b.cc': 'blo', 'b.cs': 'bhs', 'bcc': 'blo', 'bcs': 'bhs',
}

SHIFT_OPS = ('lsl', 'lsr', 'asr')

CHAR_ESCAPES = {'n': 10, 't': 9, 'r': 13, '0': 0, '\\': 92, "'": 39, '"': 34}


def strip_source_line(line):
    # Remove a // comment and any labels in front of the instruction
    text = line.split('//', 1)[0].strip()
    while True:
        label = re.match(r'^[A-Za-z_.$][\w.$]*:\s*', text)
        if not label:
            return text
        text = text[label.end():].strip()


def parse_register(text):
    name = text.lower()
    if name in ('sp', 'wsp'):
        return {'kind': 'reg', 'name': name, 'number': None, 'bits': 64 if name == 'sp' else 32, 'special': 'sp'}
    if name in ('xzr', 'wzr'):
        return {'kind': 'reg', 'name': name, 'number': None, 'bits': 64 if name == 'xzr' else 32, 'special': 'zr'}
    match = re.fullmatch(r'([xw])(\d+)', name)
    if match and int(match.group(2)) <= 30:
        return {'kind': 'reg', 'name': name, 'number': int(match.group(2)),
                'bits': 64 if match.group(1) == 'x' else 32, 'special': None}
    return None


def parse_number(text):
    text = text.strip()
    if text.startswith('#'):
        text = text[1:].strip()
    char = re.fullmatch(r"'(\\?.)'", text)
    if char:
        body = char.group(1)
        if len(body) == 2:
            return CHAR_ESCAPES.get(body[1])
        return ord(body)
    try:
        return int(text, 0)
    except ValueError:
        return None


def parse_immediate(text):
    text = text.strip()
    return {'kind': 'imm', 'text': text.lstrip('#').strip(), 'value': parse_number(text)}


def parse_shift(text):
    match = re.fullmatch(r'(lsl|lsr|asr)\s+(#?\s*\S+)', text.strip().lower())
    if not match:
        return None
    return {'kind': 'shift', 'op': match.group(1), 'amount': parse_immediate(match.group(2))}


# Split on commas that are outside brackets and quotes
def split_operands(text):
    parts, depth, quote, current = [], 0, False, ''
    for char in text:
        if char == "'":
            quote = not quote
        elif not quote and char == '[':
            depth += 1
        elif not quote and char == ']':
            depth -= 1
        if char == ',' and depth == 0 and not quote:
            parts.append(current.strip())
            current = ''
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def parse_memory(text):
    match = re.fullmatch(r'\[(.*)\]\s*(!?)', text.strip())
    if not match:
        return None
    pieces = [piece.strip() for piece in match.group(1).split(',')]
    base = parse_register(pieces[0])
    if base is None or base['bits'] != 64 or base['special'] == 'zr':
        return None
    operand = {'kind': 'mem', 'base': base, 'offset': None, 'index': None, 'shift': None,
               'mode': 'pre' if match.group(2) else 'offset', 'text': text.strip()}
    if len(pieces) >= 2:
        index = parse_register(pieces[1])
        if index is not None:
            operand['index'] = index
        else:
            operand['offset'] = parse_immediate(pieces[1])
    if len(pieces) == 3:
        shift = parse_shift(pieces[2])
        if shift is None or operand['index'] is None or shift['op'] != 'lsl':
            return None  # extends such as sxtw are not covered
        operand['shift'] = shift
    if len(pieces) > 3 or (operand['mode'] == 'pre' and operand['offset'] is None):
        return None
    return operand


def parse_operand(text):
    if text.startswith('['):
        return parse_memory(text)
    register = parse_register(text)
    if register is not None:
        return register
    shift = parse_shift(text)
    if shift is not None:
        return shift
    if text.startswith('#') or parse_number(text) is not None:
        return parse_immediate(text)
    if re.fullmatch(r'[A-Za-z_.$][\w.$]*', text):
        return {'kind': 'label', 'name': text}
    # Expressions such as N-1 are kept as symbolic immediates
    return {'kind': 'imm', 'text': text, 'value': None}


def parse_instruction(line):
    text = strip_source_line(line)
    if not text or text.startswith('.'):
        return None
    parts = text.split(None, 1)
    mnemonic = parts[0].lower()
    mnemonic = BRANCH_ALIASES.get(mnemonic, mnemonic)
    operand_texts = split_operands(parts[1]) if len(parts) > 1 else []
    operands = []
    for operand_text in operand_texts:
        operand = parse_operand(operand_text)
        if operand is None:
            return {'mnemonic': mnemonic, 'operands': None, 'text': text}
        operands.append(operand)

    # Post-index: "[xn], 8" turns into one memory operand with mode 'post'
    if (len(operands) >= 2 and operands[-2]['kind'] == 'mem' and operands[-2]['mode'] == 'offset'
            and operands[-2]['offset'] is None and operands[-2]['index'] is None and operands[-1]['kind'] == 'imm'):
        memory = dict(operands[-2], mode='post', offset=operands[-1])
        operands = operands[:-2] + [memory]

    return {'mnemonic': mnemonic, 'operands': operands, 'text': text}
