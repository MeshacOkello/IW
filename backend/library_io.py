"""Limited LP64/AAPCS64 stdio simulation over Unicorn memory and byte streams."""
import re

from heap import HEAP_END, HEAP_START, HeapError

MAX_IO_BYTES = 1 << 16
MAX_STREAM_BYTES = 1 << 20
WHITESPACE = b' \t\n\r\v\f'


class LibraryError(HeapError):
    pass


class InputProtocolError(ValueError):
    pass


class WaitingForInput(Exception):
    def __init__(self, pending):
        self.pending = pending


class LibraryMemory:
    def __init__(self, cpu, heap, regions, record_access):
        self.cpu = cpu
        self.heap = heap
        self.regions = regions
        self.record_access = record_access

    def validate(self, address, size, kind):
        if size == 0:
            return
        region = next((region for region in self.regions if region[0] <= address
                       and address + size <= region[1]), None)
        pointer = {'kind': 'address', 'value': str(address)}
        if region is None or address == 0:
            raise LibraryError(f'invalid {size}-byte {kind} at ', pointer)
        if kind == 'write' and not region[2]:
            raise LibraryError('write into read-only memory at ', pointer)
        if address < HEAP_END and address + size > HEAP_START:
            # Validate before writing without marking any bytes initialized.
            self.heap.record_access(address, size, 'read')

    def read(self, address, size, *, record=True):
        self.validate(address, size, 'read')
        data = bytes(self.cpu.mem_read(address, size)) if size else b''
        if record and size:
            self.record_access('read', address, size)
        return data

    def write(self, address, data):
        self.validate(address, len(data), 'write')
        if data:
            self.cpu.mem_write(address, data)
            # Unicorn's Python memory API bypasses CPU access hooks.
            self.record_access('write', address, len(data))

    def c_string(self, address):
        result = bytearray()
        for offset in range(MAX_IO_BYTES):
            try:
                byte = self.read(address + offset, 1, record=False)[0]
            except LibraryError as error:
                if offset == 0:
                    raise
                raise LibraryError('unterminated string before unreadable memory at ',
                                   {'kind': 'address', 'value': str(address + offset)}) from error
            if byte == 0:
                self.record_access('read', address, offset + 1)
                return bytes(result)
            result.append(byte)
        raise LibraryError('unterminated string within 65536 bytes at ',
                           {'kind': 'address', 'value': str(address)})


def integer(value, bits, signed=False):
    value &= (1 << bits) - 1
    return value - (1 << bits) if signed and value & (1 << (bits - 1)) else value


def printf_parts(fmt):
    parts = []
    literal = bytearray()
    index = 0
    while index < len(fmt):
        byte = fmt[index]
        index += 1
        if byte != ord('%'):
            literal.append(byte)
            continue
        if index < len(fmt) and fmt[index] == ord('%'):
            literal.append(ord('%'))
            index += 1
            continue
        if literal:
            parts.append(bytes(literal))
            literal.clear()
        modifier = b''
        if index < len(fmt) and fmt[index] == ord('l'):
            modifier = b'l'
            index += 1
        if index >= len(fmt):
            raise LibraryError('unsupported or incomplete printf format')
        conversion = modifier + bytes([fmt[index]])
        index += 1
        if conversion not in (b'd', b'u', b'ld', b'lu', b'c', b's', b'p'):
            raise LibraryError('unsupported printf conversion or modifier')
        parts.append(conversion.decode('ascii'))
    if literal:
        parts.append(bytes(literal))
    return parts


class Stdio:
    def __init__(self, events):
        self.events = events
        self.event_index = 0
        self.input = bytearray()
        self.position = 0
        self.eof = False
        self.output = []
        self.output_size = 0
        self.prompt_start = 0

    def input_byte(self, position, context):
        while position >= len(self.input) and not self.eof:
            pending = {
                **context, 'request_id': f"{context['occurrence']}:{self.event_index}",
                'stdout_start': self.prompt_start,
            }
            if self.event_index == len(self.events):
                raise WaitingForInput(pending)
            event = self.events[self.event_index]
            if event.get('request_id') != pending['request_id']:
                raise InputProtocolError('input submission does not match the waiting execution occurrence')
            eof = event.get('eof') is True
            text = event.get('text', '') if eof else event.get('text')
            if not isinstance(text, str) or ('eof' in event and not eof):
                raise InputProtocolError('submit text or text with explicit EOF')
            try:
                data = (text + ('' if eof else '\n')).encode('utf-8')
            except UnicodeEncodeError as error:
                raise InputProtocolError('input text must contain valid Unicode') from error
            if len(self.input) + len(data) > MAX_STREAM_BYTES:
                raise InputProtocolError('simulated stdin exceeds 1 MiB')
            self.input.extend(data)
            self.eof = eof
            self.event_index += 1
        return self.input[position] if position < len(self.input) else None

    def emit(self, data):
        if self.output_size + len(data) > MAX_STREAM_BYTES:
            raise LibraryError('simulated stdout exceeds 1 MiB')
        if data:
            self.output.append(data.hex())
            self.output_size += len(data)

    def call(self, name, argument, memory, context):
        if name == 'printf':
            parts = printf_parts(memory.c_string(argument(0)))
            output = bytearray()
            index = 1
            for part in parts:
                if isinstance(part, bytes):
                    output.extend(part)
                else:
                    value = argument(index)
                    index += 1
                    if part in ('d', 'u', 'ld', 'lu'):
                        bits = 64 if part.startswith('l') else 32
                        output.extend(str(integer(value, bits, part.endswith('d'))).encode('ascii'))
                    elif part == 'c':
                        output.append(value & 255)
                    elif part == 's':
                        output.extend(memory.c_string(value))
                    else:
                        output.extend(f'0x{value:x}'.encode('ascii'))
                if len(output) > MAX_IO_BYTES:
                    raise LibraryError('printf output exceeds 65536 bytes per call')
            self.emit(output)
            return len(output)
        if name == 'puts':
            self.emit(memory.c_string(argument(0)) + b'\n')
            return 0
        if name == 'putchar':
            value = argument(0) & 255
            self.emit(bytes([value]))
            return value
        if name == 'getchar':
            value = self.input_byte(self.position, context)
            if value is None:
                return 0xffffffff
            self.position += 1
            return value
        if name == 'fgets':
            destination, count = argument(0), integer(argument(1), 32, True)
            if argument(2) != 0:
                raise LibraryError('fgets supports simulated stdin only; pass x2 = 0')
            if not 1 <= count <= MAX_IO_BYTES:
                raise LibraryError('fgets requires a buffer size from 1 to 65536')
            position = self.position
            data = bytearray()
            while len(data) < count - 1:
                byte = self.input_byte(position, context)
                if byte is None:
                    if not data:
                        self.position = position
                        return 0
                    break
                data.append(byte)
                position += 1
                if byte == 10:
                    break
            memory.write(destination, bytes(data) + b'\0')
            self.position = position
            return destination
        if name == 'scanf':
            fmt = memory.c_string(argument(0))
            match = re.fullmatch(rb'[ \t\n\r\v\f]*%(l?d)([ \t\n\r\v\f]*)', fmt)
            if not match:
                raise LibraryError('scanf supports exactly one %d or %ld conversion with optional whitespace')
            position = self.position
            byte = self.input_byte(position, context)
            while byte is not None and byte in WHITESPACE:
                position += 1
                byte = self.input_byte(position, context)
            if byte is None:
                self.position = position
                return 0xffffffff
            sign = 1
            if byte in (ord('+'), ord('-')):
                sign = -1 if byte == ord('-') else 1
                position += 1
                byte = self.input_byte(position, context)
            size = 8 if match[1] == b'ld' else 4
            limit = (1 << (size * 8 - 1)) - (1 if sign > 0 else 0)
            value = 0
            have_digits = False
            while byte is not None and ord('0') <= byte <= ord('9'):
                have_digits = True
                value = value * 10 + byte - ord('0')
                if value > limit:
                    raise LibraryError('scanf integer is outside the destination type range')
                position += 1
                byte = self.input_byte(position, context)
            if not have_digits:
                self.position = position
                return 0
            value *= sign
            if match[2]:
                while byte is not None and byte in WHITESPACE:
                    position += 1
                    byte = self.input_byte(position, context)
            memory.write(argument(1), value.to_bytes(size, 'little', signed=True))
            self.position = position
            return 1
        raise LibraryError(f'unsupported library call {name}')
