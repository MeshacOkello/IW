"""Allocation and snapshot bookkeeping for the simulator's Unicorn heap."""
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass

HEAP_START = 0x400000
HEAP_SIZE = 0x4000
HEAP_END = HEAP_START + HEAP_SIZE
HEAP_ALIGNMENT = 16
SNAPSHOT_CHUNK_SIZE = 256
# Library functions a program may call with bl. A label of the same name in
# the program takes precedence, so a student's own labs or puts runs as code.
# New names go at the end so existing call addresses do not move.
LIBRARY_SYMBOLS = {
    name: 0x410000 + index * 4
    for index, name in enumerate(
        ('malloc', 'free', 'printf', 'puts', 'putchar', 'getchar', 'fgets', 'scanf', 'labs',
         'isspace', 'memset', 'calloc', 'exit'))
}
LONG_MIN = -(1 << 63)


def labs(value):
    """C's labs on the unsigned 64-bit contents of x0, read as a signed long.

    LONG_MIN has no positive counterpart in a long. C leaves labs(LONG_MIN)
    undefined; the AArch64 C library computes it with a negate that wraps, so
    it returns LONG_MIN unchanged, and the simulator does the same rather than
    stopping a program that would run on the real machine.
    """
    signed = value - (1 << 64) if value >= 1 << 63 else value
    return abs(signed) & ((1 << 64) - 1) if signed != LONG_MIN else value



class HeapError(ValueError):
    """A memory fault the simulator detected itself.

    `parts` keeps addresses as data so the frontend can show them in the
    student's chosen base. `kind` is the error taxonomy from errors.py:
    'runtime' for a fault in the program, 'unsupported' for a library feature
    the simulator does not provide.
    """

    def __init__(self, *parts, kind='runtime'):
        self.parts = parts
        self.kind = kind
        super().__init__(''.join(
            part if isinstance(part, str) else (
                hex(int(part['value'])) if part['kind'] == 'address' else part['value']
            )
            for part in parts
        ))


@dataclass
class Allocation:
    address: int
    size: int
    reserved: int
    initialized: bytearray
    contents: bytes | None = None
    snapshot_id: int | None = None
    initialized_changed: bool = False
    # The snapshot chunks written since the last snapshot, or None when the
    # whole allocation has to be read again. A large allocation is then only
    # re-read and re-chunked where a step actually stored into it.
    dirty: set | None = None
    chunk_ids: list | None = None


class Heap:
    def __init__(self, start=HEAP_START, size=HEAP_SIZE):
        self.start = start
        self.size = size
        self.end = start + size
        self.available = [(start, size)]
        self.active = {}
        self.starts = []
        self.freed = bytearray(size)
        self.freed_starts = set()
        self.snapshots = []
        self.chunks = []
        self.chunk_ids = {}

    def malloc(self, size):
        # Reserve a gap after each payload to catch ordinary overruns even
        # when another allocation is live immediately after it.
        alignment = HEAP_ALIGNMENT
        reserved = ((max(size, 1) + alignment - 1) // alignment + 1) * alignment
        for index, (address, length) in enumerate(self.available):
            if reserved > length:
                continue
            if reserved == length:
                self.available.pop(index)
            else:
                self.available[index] = (address + reserved, length - reserved)
            self.active[address] = Allocation(address, size, reserved, bytearray(size))
            insort(self.starts, address)
            offset = address - self.start
            self.freed[offset:offset + reserved] = bytes(reserved)
            self.freed_starts.discard(address)
            return address
        return 0

    def calloc(self, count, size, write_memory):
        """malloc for count * size bytes, zeroed and counted as written."""
        total = count * size
        if total >= 1 << 64:
            return 0
        address = self.malloc(total)
        if address and total:
            write_memory(address, bytes(total))
            self.active[address].initialized[:] = b'\x01' * total
        return address

    def mark_all_dirty(self):
        """Memory changed without the access hooks seeing it."""
        for allocation in self.active.values():
            allocation.dirty = None

    def allocation_at(self, address):
        index = bisect_right(self.starts, address) - 1
        if index >= 0:
            allocation = self.active[self.starts[index]]
            if address < allocation.address + allocation.reserved:
                return allocation
        return None

    def free(self, address):
        if address == 0:
            return
        allocation = self.active.pop(address, None)
        if allocation is None:
            pointer = {'kind': 'address', 'value': str(address)}
            if address in self.freed_starts and self.allocation_at(address) is None:
                raise HeapError('double free at ', pointer)
            raise HeapError('invalid free at ', pointer, '; expected the start of a live allocation')

        self.starts.pop(bisect_left(self.starts, address))
        self.freed_starts.add(address)
        offset = address - self.start
        self.freed[offset:offset + allocation.size] = b'\x01' * allocation.size

        size = allocation.reserved
        index = bisect_left(self.available, (address,))
        if index:
            previous, length = self.available[index - 1]
            if previous + length == address:
                address = previous
                size += length
                index -= 1
                self.available.pop(index)
        if index < len(self.available):
            following, length = self.available[index]
            if address + size == following:
                size += length
                self.available.pop(index)
        self.available.insert(index, (address, size))

    def record_access(self, address, size, kind):
        end = address + size
        if address >= self.end or end <= self.start:
            return

        allocation = self.allocation_at(address)
        if allocation and end <= allocation.address + allocation.size:
            if kind == 'write':
                offset = address - allocation.address
                if allocation.dirty is not None:
                    allocation.dirty.update(range(
                        offset // SNAPSHOT_CHUNK_SIZE,
                        (offset + size - 1) // SNAPSHOT_CHUNK_SIZE + 1))
                initialized = allocation.initialized
                if 0 in initialized[offset:offset + size]:
                    initialized[offset:offset + size] = b'\x01' * size
                    allocation.initialized_changed = True
            return

        offset = address - self.start
        problem = 'out-of-bounds heap access'
        if allocation is None and 0 <= offset < self.size and self.freed[offset]:
            problem = 'use-after-free'
        raise HeapError(
            f'{problem}: ', {'kind': 'data', 'value': str(size)},
            f'-byte {kind} at ', {'kind': 'address', 'value': str(address)},
        )

    def snapshot(self, read_memory):
        active_snapshots = []
        for address in self.starts:
            allocation = self.active[address]
            if allocation.dirty is not None and not allocation.dirty and not allocation.initialized_changed:
                active_snapshots.append(allocation.snapshot_id)
                continue
            data = bytes(read_memory(address, allocation.size)) if allocation.size else b''
            if data != allocation.contents or allocation.initialized_changed:
                # Reuse unchanged chunks across versions so a one-byte
                # write does not copy a large allocation into the trace.
                previous = allocation.chunk_ids
                # Every write marks its chunks dirty before it marks bytes
                # initialized, so the dirty chunks cover both kinds of change.
                full = previous is None or allocation.dirty is None
                if full:
                    offsets = range(0, allocation.size, SNAPSHOT_CHUNK_SIZE)
                    chunks = []
                else:
                    offsets = sorted(index * SNAPSHOT_CHUNK_SIZE for index in allocation.dirty)
                    chunks = list(previous)
                for offset in offsets:
                    end = offset + SNAPSHOT_CHUNK_SIZE
                    block = data[offset:end]
                    initialized = bytes(allocation.initialized[offset:end])
                    key = (block, initialized)
                    chunk_id = self.chunk_ids.get(key)
                    if chunk_id is None:
                        chunk_id = len(self.chunks)
                        self.chunk_ids[key] = chunk_id
                        if 0 in initialized:
                            contents = ''.join(f'{byte:02x}' if known else '??'
                                               for byte, known in zip(block, initialized))
                        else:
                            contents = block.hex()
                        self.chunks.append(contents)
                    if full:
                        chunks.append(chunk_id)
                    else:
                        chunks[offset // SNAPSHOT_CHUNK_SIZE] = chunk_id
                allocation.contents = data
                allocation.chunk_ids = chunks
                allocation.initialized_changed = False
                allocation.snapshot_id = len(self.snapshots)
                self.snapshots.append({'address': address, 'size': allocation.size, 'chunks': chunks})
            allocation.dirty = set()
            active_snapshots.append(allocation.snapshot_id)
        return active_snapshots
