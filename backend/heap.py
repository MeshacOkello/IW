"""Allocation and snapshot bookkeeping for the simulator's Unicorn heap."""
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass

HEAP_START = 0x400000
HEAP_SIZE = 0x4000
HEAP_END = HEAP_START + HEAP_SIZE
HEAP_ALIGNMENT = 16
SNAPSHOT_CHUNK_SIZE = 256
LIBRARY_SYMBOLS = {'malloc': 0x410000, 'free': 0x410004}


class HeapError(ValueError):
    def __init__(self, *parts):
        self.parts = parts
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


class Heap:
    def __init__(self):
        self.available = [(HEAP_START, HEAP_SIZE)]
        self.active = {}
        self.starts = []
        self.freed = bytearray(HEAP_SIZE)
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
            offset = address - HEAP_START
            self.freed[offset:offset + reserved] = bytes(reserved)
            self.freed_starts.discard(address)
            return address
        return 0

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
        offset = address - HEAP_START
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
        if address >= HEAP_END or end <= HEAP_START:
            return

        allocation = self.allocation_at(address)
        if allocation and end <= allocation.address + allocation.size:
            if kind == 'write':
                offset = address - allocation.address
                initialized = allocation.initialized
                if 0 in initialized[offset:offset + size]:
                    initialized[offset:offset + size] = b'\x01' * size
                    allocation.initialized_changed = True
            return

        offset = address - HEAP_START
        problem = 'out-of-bounds heap access'
        if allocation is None and 0 <= offset < HEAP_SIZE and self.freed[offset]:
            problem = 'use-after-free'
        raise HeapError(
            f'{problem}: ', {'kind': 'data', 'value': str(size)},
            f'-byte {kind} at ', {'kind': 'address', 'value': str(address)},
        )

    def snapshot(self, read_memory):
        active_snapshots = []
        for address in self.starts:
            allocation = self.active[address]
            data = bytes(read_memory(address, allocation.size)) if allocation.size else b''
            if data != allocation.contents or allocation.initialized_changed:
                # Reuse unchanged chunks across versions so a one-byte
                # write does not copy a large allocation into the trace.
                chunks = []
                for offset in range(0, allocation.size, SNAPSHOT_CHUNK_SIZE):
                    end = offset + SNAPSHOT_CHUNK_SIZE
                    block = data[offset:end]
                    initialized = bytes(allocation.initialized[offset:end])
                    key = (block, initialized)
                    chunk_id = self.chunk_ids.get(key)
                    if chunk_id is None:
                        chunk_id = len(self.chunks)
                        self.chunk_ids[key] = chunk_id
                        contents = ''.join(f'{byte:02x}' if known else '??' for byte, known in zip(block, initialized))
                        self.chunks.append(contents)
                    chunks.append(chunk_id)
                allocation.contents = data
                allocation.initialized_changed = False
                allocation.snapshot_id = len(self.snapshots)
                self.snapshots.append({'address': address, 'size': allocation.size, 'chunks': chunks})
            active_snapshots.append(allocation.snapshot_id)
        return active_snapshots
