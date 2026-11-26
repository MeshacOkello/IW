import time

from unicorn import (
    Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ,
    UC_HOOK_MEM_INVALID, UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED, UC_MEM_WRITE,
    UC_MEM_READ_UNMAPPED, UC_MEM_READ_PROT, UC_MEM_WRITE_UNMAPPED, UC_MEM_WRITE_PROT,
    UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC, UC_PROT_ALL,
)
import unicorn.arm64_const as reg

import errors
import linker
from assembler import STACK_START, STACK_END, TEXT_START, assemble_program, page_size
from heap import LIBRARY_SYMBOLS, Heap, HeapError, labs
from instruction_parser import parse_instruction
from library_io import (
    InputProtocolError, LibraryError, LibraryMemory, Stdio, WaitingForInput, isspace,
)
from pointer_registers import PC as PC_INDEX, SP as SP_INDEX, pointer_registers_after

LIBRARY_TARGETS = {address: name for name, address in LIBRARY_SYMBOLS.items()}

# A runaway recursion never returns, and every recorded step keeps a snapshot
# of every live call, so an uncapped depth makes the trace grow with the square
# of the step count. The simulated stack is 4 KiB, which a real recursive
# function exhausts well before this depth.
MAX_CALL_DEPTH = 256

# Linked code runs at full speed between recorded steps; this bounds one such
# stretch, so a program that corrupts its caller cannot hang the backend.
LINKED_TIME_LIMIT = 10.0
# The most memset may fill in one call.
MAX_MEMSET_BYTES = 1 << 24
CALLEE_SAVED = range(19, 30)


class ProgramExit(Exception):
    """The program called exit."""

    def __init__(self, status):
        super().__init__(status)
        self.status = status


class LinkedCodeError(Exception):
    """Linked code could not continue: it faulted, called a missing function,
    or ran past the time limit. The message completes a sentence about it."""

    def __init__(self, message, suggestion=None, detail=None):
        super().__init__(message)
        self.message = message
        self.suggestion = suggestion
        self.detail = detail


def error_status(error):
    """Wrap a structured error as a trace status, keeping the flat fields."""
    status = {'state': 'error', 'error_info': error, 'error': errors.legacy_text(error)}
    parts = errors.legacy_parts(error)
    if parts:
        status['error_parts'] = parts
    if error.get('line') is not None:
        status['line'] = error['line']
    return status


# Named for messages, so a fault can say which region an address lands in.
def memory_region_names(program, heap, link=None):
    return tuple(
        [(section.address, section.address + section.size, section.name)
         for section in program.sections if section.size]
        + [(STACK_START, STACK_END, 'the stack'), (heap.start, heap.end, 'the heap')]
        + [(bundle.base, bundle.end, 'library code') for bundle in (link.bundles if link else ())]
    )


# The invalid-access kinds Unicorn reports, mapped to the word used in messages.
FAULT_KINDS = {
    UC_MEM_READ_UNMAPPED: 'read', UC_MEM_READ_PROT: 'read',
    UC_MEM_WRITE_UNMAPPED: 'write', UC_MEM_WRITE_PROT: 'write',
}

# Dictionary that maps register name to its Unicorn register identifier (just for simplicity)
registers = {
    'x0':reg.UC_ARM64_REG_X0,
    'x1': reg.UC_ARM64_REG_X1,
    'x2': reg.UC_ARM64_REG_X2,
    'x3': reg.UC_ARM64_REG_X3,
    'x4': reg.UC_ARM64_REG_X4,
    'x5': reg.UC_ARM64_REG_X5,
    'x6': reg.UC_ARM64_REG_X6,
    'x7': reg.UC_ARM64_REG_X7,
    'x8': reg.UC_ARM64_REG_X8,
    'x9': reg.UC_ARM64_REG_X9,
    'x10': reg.UC_ARM64_REG_X10,
    'x11': reg.UC_ARM64_REG_X11,
    'x12': reg.UC_ARM64_REG_X12,
    'x13': reg.UC_ARM64_REG_X13,
    'x14': reg.UC_ARM64_REG_X14,
    'x15': reg.UC_ARM64_REG_X15,
    'x16': reg.UC_ARM64_REG_X16,
    'x17': reg.UC_ARM64_REG_X17,
    'x18': reg.UC_ARM64_REG_X18,
    'x19': reg.UC_ARM64_REG_X19,
    'x20': reg.UC_ARM64_REG_X20,
    'x21': reg.UC_ARM64_REG_X21,
    'x22': reg.UC_ARM64_REG_X22,
    'x23': reg.UC_ARM64_REG_X23,
    'x24': reg.UC_ARM64_REG_X24,
    'x25': reg.UC_ARM64_REG_X25,
    'x26': reg.UC_ARM64_REG_X26,
    'x27': reg.UC_ARM64_REG_X27,
    'x28': reg.UC_ARM64_REG_X28,
    'x29': reg.UC_ARM64_REG_X29,
    'x30': reg.UC_ARM64_REG_X30,
    'sp': reg.UC_ARM64_REG_SP,
    'pc': reg.UC_ARM64_REG_PC,
    'nzcv': reg.UC_ARM64_REG_NZCV,

}


# A section's bytes, in the hex form the heap already uses for its contents.
def read_section(read_memory, section):
    return bytes(read_memory(section.address, section.size)).hex()


def written_in(accesses, section):
    return any(
        access['kind'] == 'write'
        and access['address'] < section.address + section.size
        and section.address < access['address'] + access['size']
        for access in accesses
    )


def run_program(program, input_events=None, execution_limit=10_000):
    # Course code the program needs but does not contain, such as the C
    # files of an assignment, is linked in here. Usually there is none.
    link = linker.link(program)
    heap = Heap(linker.LINKED_HEAP_START, linker.LINKED_HEAP_SIZE) if link else Heap()
    cpu_emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_NZCV, 0)

    permissions = {
        '.text': UC_PROT_READ | UC_PROT_EXEC,
        '.data': UC_PROT_READ | UC_PROT_WRITE,
        '.rodata': UC_PROT_READ,
        '.bss': UC_PROT_READ | UC_PROT_WRITE,
    }
    for section in program.sections:
        if section.size:
            cpu_emulator.mem_map(section.address, page_size(section.size), permissions[section.name])
            if section.data:
                cpu_emulator.mem_write(section.address, section.data)

    cpu_emulator.mem_map(STACK_START, STACK_END - STACK_START, UC_PROT_READ | UC_PROT_WRITE)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_SP, STACK_END)
    cpu_emulator.mem_map(heap.start, heap.size, UC_PROT_READ | UC_PROT_WRITE)
    for bundle in link.bundles if link else ():
        cpu_emulator.mem_map(bundle.base, bundle.mapped_size, UC_PROT_READ | UC_PROT_WRITE)  # executable only while it runs
        cpu_emulator.mem_write(bundle.base, bundle.image)
    for slot, target in (link.slot_targets.items() if link else ()):
        cpu_emulator.mem_write(slot, target.to_bytes(8, 'little'))

    address_to_labels = {}
    for label, address in program.symbols.items():
        if address in program.instructions:
            address_to_labels.setdefault(address, []).append(label)
    data_sections = [
        section for section in program.sections
        if section.name != '.text' and section.size
    ]
    text = next(section for section in program.sections if section.name == '.text')
    return record_register_states(
        cpu_emulator, program.instructions, address_to_labels, program.symbols, data_sections,
        input_events or [], execution_limit,
        [(section.address, section.address + section.size, section.name in ('.data', '.bss'))
         for section in program.sections if section.size]
        + [(STACK_START, STACK_END, True), (heap.start, heap.end, True)]
        + [(bundle.base, bundle.end, True) for bundle in (link.bundles if link else ())],
        memory_region_names(program, heap, link),
        heap=heap, link=link, text=(text.address, page_size(max(text.size, 1))),
    )


# The stack is tracked as a sorted list of non-overlapping cells
# {'address', 'size', 'written'}. A blank cell (written == False) is
# reserved space that nothing has been stored into yet.

# Add a written cell, splitting any cells the write overlaps
def record_stack_write(stack_cells, address, size):
    end = address + size
    updated_cells = []
    for cell in stack_cells:
        cell_end = cell['address'] + cell['size']
        if cell_end <= address or cell['address'] >= end:
            updated_cells.append(cell)
            continue
        # Keep the parts of the old cell that lie outside the write
        if cell['address'] < address:
            updated_cells.append({'address': cell['address'], 'size': address - cell['address'], 'written': cell['written']})
        if cell_end > end:
            updated_cells.append({'address': end, 'size': cell_end - end, 'written': cell['written']})
    updated_cells.append({'address': address, 'size': size, 'written': True})
    return sorted(updated_cells, key=lambda cell: cell['address'])

# sp moved down: the newly reserved space becomes a blank cell,
# except where something has already been written
def reserve_stack(stack_cells, new_sp, old_sp):
    high = min(old_sp, STACK_END)
    cursor = max(new_sp, STACK_START)
    blank_cells = []
    for cell in stack_cells:
        cell_end = cell['address'] + cell['size']
        if cell_end <= cursor or cell['address'] >= high:
            continue
        if cell['address'] > cursor:
            blank_cells.append({'address': cursor, 'size': cell['address'] - cursor, 'written': False})
        cursor = cell_end
    if cursor < high:
        blank_cells.append({'address': cursor, 'size': high - cursor, 'written': False})
    return sorted(stack_cells + blank_cells, key=lambda cell: cell['address'])

# sp moved up: everything below it is released
def release_stack(stack_cells, new_sp):
    kept_cells = []
    for cell in stack_cells:
        cell_end = cell['address'] + cell['size']
        if cell_end <= new_sp:
            continue
        if cell['address'] < new_sp:
            cell = {'address': new_sp, 'size': cell_end - new_sp, 'written': cell['written']}
        kept_cells.append(cell)
    return kept_cells

# Unicorn reports a store of a 128-bit q register as two 8-byte writes.
# Detect instructions that store whole q registers so the halves can be rejoined.
def stores_q_registers(instruction):
    if (instruction >> 26) & 1 == 0:  # not a SIMD&FP load/store
        return False
    group = (instruction >> 27) & 0b111
    if group == 0b111 and (instruction >> 25) & 1 == 0:
        # STR/STUR (SIMD&FP): size == 00, opc == 10
        return (instruction >> 30) == 0b00 and ((instruction >> 22) & 0b11) == 0b10
    if group == 0b101 and (instruction >> 25) & 1 == 0:
        # STP/STNP (SIMD&FP): opc == 10, L == 0
        return (instruction >> 30) == 0b10 and ((instruction >> 22) & 1) == 0
    # ST1 (multiple structures) with Q == 1: one to four whole registers
    return ((instruction >> 30) == 0b01 and ((instruction >> 24) & 0b111111) == 0b001100
            and ((instruction >> 22) & 1) == 0 and ((instruction >> 12) & 0b1111) in (0b0111, 0b1010, 0b0110, 0b0010))

def join_q_register_halves(stack_writes):
    halves = list(zip(stack_writes[0::2], stack_writes[1::2]))
    if len(stack_writes) % 2 or not all(low[1] == 8 and high == (low[0] + 8, 8) for low, high in halves):
        return stack_writes
    return [(low[0], 16) for low, _ in halves]

# Apply one executed instruction's stack writes and sp change to the cells
def update_stack_cells(stack_cells, stack_writes, instruction, old_sp, new_sp):
    if stores_q_registers(instruction):
        stack_writes = join_q_register_halves(stack_writes)
    for address, size in stack_writes:
        stack_cells = record_stack_write(stack_cells, address, size)
    if new_sp > old_sp:
        stack_cells = release_stack(stack_cells, new_sp)
    elif new_sp < old_sp:
        stack_cells = reserve_stack(stack_cells, new_sp, old_sp)
    return stack_cells

# Get the cells between sp and the top of the stack. Written cells hold the
# value currently in memory; blank cells have no value.
def read_stack(cpu_emulator, stack_cells, sp):
    stack_snapshot = []

    for cell in stack_cells:
        start = max(cell['address'], sp)
        end = cell['address'] + cell['size']

        if start >= end:
            continue

        if cell['written']:
            value = int.from_bytes(
                cpu_emulator.mem_read(start, end - start),
                byteorder="little",
            )

            stack_snapshot.append({
                'address': start,
                'size': end - start,
                'value': value,
            })
        else:
            # Show unwritten memory in slots of at most 8 bytes.
            cursor = start

            while cursor < end:
                next_boundary = ((cursor // 8) + 1) * 8
                slot_end = min(next_boundary, end)

                stack_snapshot.append({
                    'address': cursor,
                    'size': slot_end - cursor,
                    'value': None,
                })

                cursor = slot_end

    return stack_snapshot


def read_all_registers_and_write_to_list(cpu_emulator):
    regs = []
    for i in range(31):
        register = (registers[f'x{i}'])
        regs.append(cpu_emulator.reg_read(register))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_SP))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_PC))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_NZCV))
    return regs



def signed32(value):
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >> 31 else value


def record_register_states(
    cpu_emulator,
    instructions,
    address_to_labels,
    symbols,
    data_sections,
    input_events,
    execution_limit,
    memory_regions,
    region_names=(),
    *,
    heap=None,
    link=None,
    text=None,
):
    register_states = []
    pointer_states = [[SP_INDEX, PC_INDEX]]
    parsed_instructions = {pc: parse_instruction(statement.text) for pc, statement in instructions.items()}
    executed_addresses = []
    instruction_number = [None]
    stack_states = []
    stack_cells = []
    stack_writes = []
    memory_accesses = [[]]
    step_accesses = []
    heap = heap if heap is not None else Heap()
    heap_states = []
    library_calls = {}
    # Steps whose instruction handed control to linked code and got it back:
    # step number -> what happened in between, for the explanation.
    transfers = {}
    stdio = Stdio(input_events)
    stdout_states = []
    status = None
    # Sections follow the heap's bookkeeping: each step names the version of
    # every section, and a version is only added when its bytes change.
    section_versions = []
    section_ids = {}
    for section in data_sections:
        section_versions.append(read_section(cpu_emulator.mem_read, section))
        section_ids[section.name] = len(section_versions) - 1
    section_states = []
    writable_sections = [section for section in data_sections if section.name != '.rodata']

    def record_write(uc, access, address, size, value, user_data):
        stack_writes.append((address, size))

    def record_access(uc, access, address, size, value, user_data):
        kind = 'write' if access == UC_MEM_WRITE else 'read'
        heap.record_access(address, size, kind)
        step_accesses.append({
            'kind': kind,
            'address': address,
            'size': size,
        })

    # Linked code runs without these hooks: its accesses are not the
    # program's steps, and a Python call per access would slow it down
    # by orders of magnitude.
    access_hooks = []

    def attach_access_hooks():
        access_hooks.append(cpu_emulator.hook_add(
            UC_HOOK_MEM_WRITE, record_write, begin=STACK_START, end=STACK_END - 1))
        access_hooks.append(cpu_emulator.hook_add(
            UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, record_access))

    def detach_access_hooks():
        while access_hooks:
            cpu_emulator.hook_del(access_hooks.pop())

    attach_access_hooks()

    # An access Unicorn refuses never reaches the hook above, and UcError
    # carries no address, so capture it here purely to describe the fault.
    # Returning False leaves the error to propagate exactly as before.
    fault = {}

    def record_fault(uc, access, address, size, value, user_data):
        fault.update(address=address, size=size, kind=FAULT_KINDS.get(access, 'fetch'))
        return False

    cpu_emulator.hook_add(UC_HOOK_MEM_INVALID, record_fault)

    def record_library_access(kind, address, size):
        access = UC_MEM_WRITE if kind == 'write' else None
        record_access(cpu_emulator, access, address, size, 0, None)
        if kind == 'write' and STACK_START <= address < STACK_END:
            record_write(cpu_emulator, access, address, size, 0, None)

    library_memory = LibraryMemory(cpu_emulator, heap, memory_regions, record_library_access)
    # Library calls made by linked code keep the heap's bookkeeping current
    # but are not shown as the step's own memory accesses.
    linked_memory = LibraryMemory(cpu_emulator, heap, memory_regions,
                                  lambda kind, address, size: heap.record_access(address, size, kind))

    def argument_reader(memory):
        def argument(index):
            if index < 8:
                return cpu_emulator.reg_read(registers[f'x{index}'])
            sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)
            return int.from_bytes(memory.read(sp + (index - 8) * 8, 8), 'little')
        return argument

    def call_library(name, memory, context):
        """Carry out one library call. Its result, if it has one, goes in x0."""
        argument = cpu_emulator.reg_read(reg.UC_ARM64_REG_X0)
        if name == 'malloc':
            result = heap.malloc(argument)
        elif name == 'calloc':
            result = heap.calloc(argument, cpu_emulator.reg_read(reg.UC_ARM64_REG_X1),
                                 cpu_emulator.mem_write)
        elif name == 'free':
            heap.free(argument)
            return
        elif name == 'labs':
            result = labs(argument)
        elif name == 'isspace':
            result = isspace(argument)
        elif name == 'memset':
            count = cpu_emulator.reg_read(reg.UC_ARM64_REG_X2)
            if count > MAX_MEMSET_BYTES:
                raise LibraryError(
                    'memset was asked to fill ', {'kind': 'data', 'value': str(count)},
                    f' bytes, more than the {MAX_MEMSET_BYTES} the simulator fills in one call.',
                    kind='unsupported')
            value = cpu_emulator.reg_read(reg.UC_ARM64_REG_X1) & 255
            memory.write(argument, bytes([value]) * count)
            result = argument
        elif name == 'exit':
            raise ProgramExit(signed32(argument))
        else:
            result = stdio.call(name, argument_reader(memory), memory, context)
            if name in ('fgets', 'getchar', 'scanf'):
                stdio.prompt_start = len(stdio.output)
        cpu_emulator.reg_write(reg.UC_ARM64_REG_X0, result)

    text_start, text_size = text if text else (TEXT_START, 0)

    def set_linked_code_running(running):
        """Make exactly one side executable: linked code while it runs, the
        program's instructions while they are recorded one step at a time.

        A branch from one side into the other then stops the CPU with a
        fetch fault at the first instruction across. Unicorn checks
        permissions only when it translates code, so the cached
        translations of both sides are dropped at every switch; a stale
        one would carry execution across unrecorded.
        """
        regions = [(bundle.base, bundle.mapped_size, running) for bundle in link.bundles]
        if text_size:
            regions.append((text_start, text_size, not running))
        for start, size, executable in regions:
            cpu_emulator.mem_protect(start, size, UC_PROT_ALL if executable else
                                     UC_PROT_READ | UC_PROT_WRITE)
            cpu_emulator.ctl_remove_cache(start, start + size)
        if text_size:
            # The program's .text is never writable.
            cpu_emulator.mem_protect(text_start, text_size,
                                     UC_PROT_READ | (0 if running else UC_PROT_EXEC))

    def run_linked(pc):
        """Run linked code from pc at full speed until control reaches one of
        the program's own instructions again, or the program ends.

        Returns ('program', address), ('returned', main's int result) or
        ('exited', status). The program's code is made non-executable for the
        duration, so entering it stops the CPU on its first instruction; a
        library call stops it the same way, at the call's unmapped address.
        """
        detach_access_hooks()
        set_linked_code_running(True)
        deadline = time.monotonic() + LINKED_TIME_LIMIT
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LinkedCodeError(
                        f'it ran for {LINKED_TIME_LIMIT:g} seconds without finishing.',
                        detail='linked code time limit')
                fault.clear()
                try:
                    cpu_emulator.emu_start(pc, linker.EXIT_ADDRESS,
                                           timeout=max(1, int(remaining * 1_000_000)))
                except UcError as error:
                    pc = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)
                    fetch = error.errno in (UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED)
                    if fetch and pc in instructions:
                        return 'program', pc
                    if fetch and pc == linker.EXIT_ADDRESS:
                        break
                    name = LIBRARY_TARGETS.get(pc) if fetch else None
                    if name is None:
                        missing = link.unresolved_name(pc) if fetch else None
                        if missing:
                            raise LinkedCodeError(
                                f'it calls {missing}, which the program does not define.',
                                suggestion=f'Define {missing} as a label on the first instruction '
                                           'of the function, and mark it with ".global".',
                                detail='undefined reference') from None
                        if fetch:
                            fault.setdefault('address', pc)
                        message, parts, suggestion, detail = errors.describe_unicorn_error(
                            error, fault, region_names)
                        raise LinkedCodeError(errors.render(parts) if parts else message,
                                              suggestion=suggestion, detail=detail) from None
                    context = {
                        'function': name, 'line': None, 'address': pc, 'step': counter,
                        'occurrence': f'{counter}:{pc:x}:{name}',
                    }
                    try:
                        call_library(name, linked_memory, context)
                    except WaitingForInput:
                        raise LinkedCodeError('it reads input, which linked code cannot do here.',
                                              detail='linked input') from None
                    pc = cpu_emulator.reg_read(reg.UC_ARM64_REG_X30)
                    continue
                if cpu_emulator.reg_read(reg.UC_ARM64_REG_PC) != linker.EXIT_ADDRESS:
                    raise LinkedCodeError(
                        f'it ran for {LINKED_TIME_LIMIT:g} seconds without finishing.',
                        detail='linked code time limit')
                break
            return 'returned', signed32(cpu_emulator.reg_read(reg.UC_ARM64_REG_X0))
        except ProgramExit as finished:
            return 'exited', finished.status
        finally:
            set_linked_code_running(False)
            attach_access_hooks()
            heap.mark_all_dirty()

    counter = 0
    instruction_indices = {pc: index for index, pc in enumerate(sorted(instructions), start=1)}
    stopping_address = max(instructions, default=TEXT_START) + 4
    returned = None
    exited = None
    # Set when the outermost function returned to linked code without
    # restoring a register it had to: a later crash is likely its result.
    unrestored = []

    def with_unrestored_note(suggestion):
        if not unrestored:
            return suggestion
        names = ', '.join(unrestored)
        note = (f"An earlier call returned with {names} changed. Its caller keeps values in "
                "x19 to x29 across calls, so a function must restore them, and sp, before "
                "it returns.")
        return f'{suggestion} {note}' if suggestion else note

    if link and link.entry is not None:
        # The linked main runs the program, as the C files of an assignment
        # do on armlab: it gets argc and argv, and returns to the system.
        PC = None
        try:
            outcome, value = run_linked(start_linked_main(cpu_emulator, link))
        except (LinkedCodeError, HeapError) as error:
            status = error_status(linked_failure(error, None, None))
            outcome, value = 'failed', None
        if outcome == 'program':
            PC = value
        elif outcome == 'returned':
            returned = {'function': 'main', 'value': value, 'step': 0}
        elif outcome == 'exited':
            exited = {'status': value, 'step': 0}
        cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC if PC is not None else linker.EXIT_ADDRESS)
    else:
        # A program with main starts there, as a C program does, wherever main
        # sits in .text. Without one, execution starts at the first instruction.
        PC = symbols['main'] if symbols.get('main') in instructions else next(iter(instruction_indices), TEXT_START)
        cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC)
    initial_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)
    # The return address the first function was entered with. A ret to it from
    # that function hands control back to the system: the program is done.
    # A function called by linked code returns there instead.
    exit_address = None if link and link.entry is not None else cpu_emulator.reg_read(reg.UC_ARM64_REG_X30)

    def frame_for(address, entry_sp, return_address):
        labels = address_to_labels.get(address, []) if address is not None else ['main']
        return {
            'id': next_frame_id,
            'name': labels[0] if labels else (f'function_{address:x}' if link and link.entry is not None else 'entry'),
            'entry_sp': entry_sp,
            'return_address': return_address,
        }

    # The initial function exists before any call instruction executes.
    next_frame_id = 0
    active_frames = [frame_for(PC, initial_sp, None)]
    next_frame_id = 1
    # What the outermost function was entered with, to tell whether it put
    # back the registers its caller relies on.
    entry_registers = read_all_registers_and_write_to_list(cpu_emulator)

    # A caller's stack space ends where its callee entered, so every frame but
    # the innermost is fixed once the next call is made. Those snapshots are
    # built once and shared across steps; only the innermost is rebuilt.
    settled_frames = []

    def settle_frame(callee_entry_sp):
        frame = active_frames[-1]
        settled_frames.append(
            dict(frame, stack_start=callee_entry_sp, stack_end=frame['entry_sp']))

    def snapshot_frames(current_sp):
        frame = active_frames[-1]
        innermost = dict(frame, stack_start=current_sp, stack_end=frame['entry_sp'])
        return settled_frames[:len(active_frames) - 1] + [innermost]

    frame_states = [snapshot_frames(initial_sp)]

    register_states.append(
        read_all_registers_and_write_to_list(cpu_emulator)
    )
    stack_states.append(
        read_stack(cpu_emulator, stack_cells, initial_sp)
    )
    executed_addresses.append(None)
    stdout_states.append(len(stdio.output))
    heap_states.append(heap.snapshot(cpu_emulator.mem_read))
    section_states.append(dict(section_ids))

    while (
        status is None
        and PC is not None
        and counter < execution_limit
        and PC in instructions
    ):
        old_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)

        instruction = int.from_bytes(
            cpu_emulator.mem_read(PC, 4),
            byteorder="little",
        )

        # Identify AArch64 call and return instructions from machine code.
        is_bl = (instruction & 0xFC000000) == 0x94000000
        is_blr = (instruction & 0xFFFFFC1F) == 0xD63F0000
        is_ret = (instruction & 0xFFFFFC1F) == 0xD65F0000

        stack_writes.clear()
        step_accesses.clear()
        fault.clear()

        library_call = None
        if is_bl:
            # BL's low 26 bits are a signed, word-scaled PC-relative offset.
            displacement = (instruction & 0x03FFFFFF) - (instruction & 0x02000000) * 2
            library_call = LIBRARY_TARGETS.get(PC + displacement * 4)

        program_exit = None
        try:
            if library_call:
                context = {
                    'function': library_call, 'line': instructions[PC].line,
                    'address': PC, 'step': counter,
                    'occurrence': f'{counter}:{PC:x}:{library_call}',
                }
                try:
                    call_library(library_call, library_memory, context)
                except ProgramExit as finished:
                    program_exit = finished.status
                library_calls[PC] = library_call
                cpu_emulator.reg_write(reg.UC_ARM64_REG_X30, PC + 4)
                cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC + 4)
            else:
                cpu_emulator.emu_start(PC, stopping_address, count=1)
        except WaitingForInput as waiting:
            status = {'state': 'waiting', 'pending': waiting.pending}
            break
        except HeapError as error:
            message = errors.render(error.parts)
            status = error_status(errors.runtime_error(
                message, parts=error.parts, line=instructions[PC].line,
                suggestion=with_unrestored_note(errors.heap_suggestion(message)), kind=error.kind,
            ))
            break
        except UcError as error:
            # Unicorn may try to fetch the branch destination before it
            # returns from a single step. Record the branch, then let the
            # instruction map stop execution at the destination.
            target = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)
            if error.errno not in (UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED) or target in instructions:
                if error.errno in (UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED):
                    fault.setdefault('address', target)
                message, parts, suggestion, detail = errors.describe_unicorn_error(
                    error, fault, region_names)
                status = error_status(errors.runtime_error(
                    message, parts=parts, line=instructions[PC].line,
                    suggestion=with_unrestored_note(suggestion), detail=detail,
                ))
                break

        # Control passed to linked code: a call to one of its functions, or
        # the outermost function returning to the linked code that called it.
        # It runs to completion here, and the step ends where control comes
        # back to the program, so the step is the call or return as a whole.
        transfer = None
        handed_to = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)
        if (link is not None and program_exit is None and handed_to not in instructions
                and link.contains(handed_to)):
            before_transfer = read_all_registers_and_write_to_list(cpu_emulator)
            returning = is_ret and len(active_frames) == 1
            function = active_frames[-1]['name']
            transfer = {
                'kind': 'return' if returning else 'call',
                'function': function if returning else link.function_at(handed_to),
                'value': before_transfer[0],
            }
            if returning:
                transfer['restored'] = restored_registers(entry_registers, before_transfer)
                unrestored = transfer['restored'] or unrestored
            try:
                outcome, value = run_linked(handed_to)
            except (LinkedCodeError, HeapError) as error:
                status = error_status(linked_failure(error, transfer, instructions[PC].line))
                outcome, value = 'failed', None
            transfer['outcome'] = outcome
            if outcome == 'program':
                transfer['resumed'] = value
                transfer['next_function'] = (address_to_labels.get(value) or [None])[0]
            elif outcome == 'returned':
                returned = {'function': 'main', 'value': value, 'step': counter + 1}
                transfer['main_value'] = value
            elif outcome == 'exited':
                program_exit = value
            if outcome != 'program':
                # Nothing of the program runs after this step. Show the state
                # as the program's own instruction left it.
                for index, register in enumerate(registers.values()):
                    cpu_emulator.reg_write(register, before_transfer[index])
                if outcome == 'failed':
                    cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, handed_to)
            transfers[counter + 1] = transfer

        if program_exit is not None:
            exited = {'status': program_exit, 'step': counter + 1}

        new_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)
        next_pc = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)

        stdout_states.append(len(stdio.output))
        memory_accesses.append(list(step_accesses))
        after = read_all_registers_and_write_to_list(cpu_emulator)
        register_states.append(after)
        if transfer:
            # Linked code ran: only the registers it had to preserve keep
            # what is known about them.
            pointer_states.append(sorted({SP_INDEX, PC_INDEX} | {
                index for index in pointer_states[-1]
                if index in CALLEE_SAVED and after[index] == register_states[-2][index]}))
        else:
            pointer_states.append(pointer_registers_after(
                pointer_states[-1], instruction, parsed_instructions[PC], symbols, after,
                link=is_bl or is_blr, library_call=library_call,
            ))

        stack_cells = update_stack_cells(
            stack_cells,
            stack_writes,
            instruction,
            old_sp,
            new_sp,
        )
        if transfer and transfer.get('outcome') == 'program' and transfer['kind'] == 'return':
            # A new outermost call begins; the stack above it belongs to
            # linked code, which is not shown.
            stack_cells = []
        stack_states.append(
            read_stack(cpu_emulator, stack_cells, new_sp)
        )

        heap_states.append(heap.snapshot(cpu_emulator.mem_read))

        # Re-read a section only when this step stored into it. Untouched
        # sections keep the version of the previous step.
        for section in writable_sections:
            if transfer or written_in(step_accesses, section):
                contents = read_section(cpu_emulator.mem_read, section)
                if contents != section_versions[section_ids[section.name]]:
                    section_versions.append(contents)
                    section_ids[section.name] = len(section_versions) - 1
        section_states.append(dict(section_ids))

        if transfer:
            if transfer.get('outcome') == 'program':
                if transfer['kind'] == 'return':
                    # Linked code called into the program again: a fresh
                    # outermost call.
                    settled_frames.clear()
                    active_frames[:] = [frame_for(next_pc, new_sp,
                                                  cpu_emulator.reg_read(reg.UC_ARM64_REG_X30))]
                    next_frame_id += 1
                    entry_registers = after
                elif next_pc != PC + 4:
                    # The linked function called back into the program.
                    settle_frame(new_sp)
                    active_frames.append(frame_for(next_pc, new_sp,
                                                   cpu_emulator.reg_read(reg.UC_ARM64_REG_X30)))
                    next_frame_id += 1
                else:
                    library_calls[PC] = transfer['function']
        elif (is_bl and not library_call) or is_blr:
            # The actual destination PC identifies the called function.
            labels = address_to_labels.get(next_pc, [])

            settle_frame(new_sp)
            active_frames.append({
                'id': next_frame_id,
                'name': labels[0] if labels else f'function_{next_pc:x}',
                'entry_sp': new_sp,
                'return_address': PC + 4,
            })
            next_frame_id += 1

        elif is_ret and len(active_frames) > 1:
            # Remove the call only if it returns to its expected caller.
            if next_pc == active_frames[-1]['return_address']:
                active_frames.pop()
                settled_frames.pop()
        elif is_ret and exit_address is not None and next_pc == exit_address:
            # main (or the first function) returned: a normal end. Its int
            # result is in w0, as the C runtime would read it.
            returned = {'function': active_frames[0]['name'],
                        'value': signed32(after[0]),
                        'step': counter + 1}

        frame_states.append(snapshot_frames(new_sp))

        executed_addresses.append(PC)
        instruction_number.append(instruction_indices[PC])
        counter += 1

        # A call that never returns would otherwise grow the trace without
        # bound: stop with a reportable error and keep every step recorded.
        if status is None and len(active_frames) > MAX_CALL_DEPTH:
            status = error_status(errors.runtime_error(
                f'The program is {MAX_CALL_DEPTH} calls deep and still has not returned.',
                line=instructions[PC].line,
                suggestion='A recursive function needs a base case that returns before '
                           'calling itself again. Check the condition that should stop it.',
                detail='call depth limit',
            ))
            break

        if returned or exited or status is not None:
            break

        PC = next_pc

    if stdio.event_index != len(input_events):
        raise InputProtocolError('input contains submissions beyond the requested execution occurrence')
    if status is None and exited:
        status = {'state': 'completed', 'exited': exited}
    if status is None and returned:
        status = {'state': 'completed', 'returned': returned}
    if status is None:
        status = {'state': 'execution_limit' if counter >= execution_limit and PC in instructions else 'completed'}

    return (
        register_states,
        stack_states,
        executed_addresses,
        instruction_number,
        memory_accesses,
        frame_states,
        heap_states,
        {'versions': heap.snapshots, 'chunks': heap.chunks},
        library_calls,
        pointer_states,
        section_states,
        section_versions,
        stdout_states,
        {'chunks': stdio.output, 'encoding': 'utf-8'},
        status,
        transfers,
    )


def restored_registers(entry, now):
    """The registers a function must hand back unchanged that it did not."""
    changed = [f'x{index}' for index in CALLEE_SAVED if entry[index] != now[index]]
    if entry[SP_INDEX] != now[SP_INDEX]:
        changed.append('sp')
    return changed


def start_linked_main(cpu_emulator, link):
    """Lay out argc and argv at the top of the stack, as Linux does, and point
    the CPU at the linked main. Returns main's address."""
    bundle = next(bundle for bundle in link.bundles if bundle.exports.get('main') == link.entry)
    arguments = linker.BUNDLE_ARGUMENTS.get(bundle.name, ('./a.out',))
    strings = b''.join(argument.encode('ascii') + b'\0' for argument in arguments)
    string_address = STACK_END - ((len(strings) + 15) // 16 * 16)
    cpu_emulator.mem_write(string_address, strings)
    pointers, offset = [], 0
    for argument in arguments:
        pointers.append(string_address + offset)
        offset += len(argument) + 1
    vector = b''.join(pointer.to_bytes(8, 'little') for pointer in pointers + [0])
    vector_address = (string_address - len(vector)) & ~15
    cpu_emulator.mem_write(vector_address, vector)
    program_name = bundle.symbols.get('__libc_program_name')
    if program_name is not None:
        cpu_emulator.mem_write(program_name, pointers[0].to_bytes(8, 'little'))
    cpu_emulator.reg_write(reg.UC_ARM64_REG_SP, vector_address)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_X0, len(arguments))
    cpu_emulator.reg_write(reg.UC_ARM64_REG_X1, vector_address)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_X30, linker.EXIT_ADDRESS)
    return link.entry


def linked_failure(error, transfer, line):
    """The error for linked code that could not go on, said from the side of
    the program's own code, which is all the student sees."""
    if isinstance(error, HeapError):
        reason = errors.render(error.parts)
        suggestion = errors.heap_suggestion(reason)
        detail = 'linked heap error'
    else:
        reason, suggestion, detail = error.message, error.suggestion, error.detail
    # Unicorn's descriptions speak of "this instruction", which here is one
    # in the calling code rather than the line shown.
    for opening, replacement in (('This instruction', 'an instruction there'),
                                 ('The program tried', 'it tried')):
        if reason.startswith(opening):
            reason = replacement + reason[len(opening):]
    reason = reason[0].lower() + reason[1:] if reason else reason
    if transfer is None:
        message = f'The program stopped before running any of its own instructions: {reason}'
    elif transfer['kind'] == 'return':
        message = f"After {transfer['function']} returned, the code that called it stopped: {reason}"
        changed = transfer.get('restored') or []
        if changed:
            names = ', '.join(changed)
            suggestion = (f"{transfer['function']} returned with {names} changed. A function must "
                          'restore x19 to x29 and sp before it returns, because its caller keeps '
                          'values there across the call. Save them in the prologue and restore '
                          'them in the epilogue.')
    else:
        message = f"{transfer['function']} stopped: {reason}"
    return errors.runtime_error(message, line=line, suggestion=suggestion, detail=detail)


def main():
    assem = """mov x1, #3
    mov x2, #0
    loop:
        add x2, x2, x1
        subs x1, x1, #1
        b.ne loop
    cmp x2, #6
    b.ne else_case
    mov x3, #100
    b end_if
    else_case:
        mov x3, #200
    end_if:
        add x4, x3, #7
    """
    print(run_program(assemble_program(assem)))

if __name__ == '__main__':
    main()

