from unicorn import (
    Uc, UcError, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ,
    UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED, UC_MEM_WRITE, UC_PROT_READ, UC_PROT_WRITE, UC_PROT_EXEC,
)
import unicorn.arm64_const as reg

from assembler import STACK_START, STACK_END, TEXT_START, assemble_program, page_size
from heap import HEAP_SIZE, HEAP_START, LIBRARY_SYMBOLS, Heap, HeapError
from instruction_parser import parse_instruction
from pointer_registers import PC as PC_INDEX, SP as SP_INDEX, pointer_registers_after

LIBRARY_TARGETS = {address: name for name, address in LIBRARY_SYMBOLS.items()}

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


def run_program(program):
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
    cpu_emulator.mem_map(HEAP_START, HEAP_SIZE, UC_PROT_READ | UC_PROT_WRITE)

    address_to_labels = {}
    for label, address in program.symbols.items():
        if address in program.instructions:
            address_to_labels.setdefault(address, []).append(label)
    return record_register_states(cpu_emulator, program.instructions, address_to_labels, program.symbols)


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



def record_register_states(
    cpu_emulator,
    instructions,
    address_to_labels,
    symbols,
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
    heap = Heap()
    heap_states = [[]]
    library_calls = {}

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

    cpu_emulator.hook_add(
        UC_HOOK_MEM_WRITE,
        record_write,
        begin=STACK_START,
        end=STACK_END - 1,
    )

    cpu_emulator.hook_add(
        UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE,
        record_access,
    )

    counter = 0
    execution_limit = 10_000
    instruction_indices = {pc: index for index, pc in enumerate(sorted(instructions), start=1)}
    PC = next(iter(instruction_indices), TEXT_START)
    stopping_address = max(instructions, default=TEXT_START) + 4

    cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC)
    initial_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)

    # The initial function exists before any call instruction executes.
    entry_labels = address_to_labels.get(PC, [])
    active_frames = [{
        'id': 0,
        'name': entry_labels[0] if entry_labels else 'entry',
        'entry_sp': initial_sp,
        'return_address': None,
    }]
    next_frame_id = 1

    def snapshot_frames(current_sp):
        snapshot = []

        for index, frame in enumerate(active_frames):
            saved_frame = frame.copy()

            # A caller's stack space ends where its callee entered.
            # The innermost function's space extends down to current SP.
            if index + 1 < len(active_frames):
                lower_address = active_frames[index + 1]['entry_sp']
            else:
                lower_address = current_sp

            saved_frame['stack_start'] = lower_address
            saved_frame['stack_end'] = frame['entry_sp']
            snapshot.append(saved_frame)

        return snapshot

    frame_states = [snapshot_frames(initial_sp)]

    register_states.append(
        read_all_registers_and_write_to_list(cpu_emulator)
    )
    stack_states.append(
        read_stack(cpu_emulator, stack_cells, initial_sp)
    )
    executed_addresses.append(None)

    while (
        counter < execution_limit
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

        library_call = None
        if is_bl:
            # BL's low 26 bits are a signed, word-scaled PC-relative offset.
            displacement = (instruction & 0x03FFFFFF) - (instruction & 0x02000000) * 2
            library_call = LIBRARY_TARGETS.get(PC + displacement * 4)

        try:
            if library_call:
                argument = cpu_emulator.reg_read(reg.UC_ARM64_REG_X0)
                if library_call == 'malloc':
                    cpu_emulator.reg_write(reg.UC_ARM64_REG_X0, heap.malloc(argument))
                else:
                    heap.free(argument)
                cpu_emulator.reg_write(reg.UC_ARM64_REG_X30, PC + 4)
                cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC + 4)
                library_calls[PC] = library_call
            else:
                cpu_emulator.emu_start(PC, stopping_address, count=1)
        except HeapError as error:
            raise HeapError(f'Line {instructions[PC].line}: ', *error.parts) from error
        except UcError as error:
            # Unicorn may try to fetch the branch destination before it
            # returns from a single step. Record the branch, then let the
            # instruction map stop execution at the destination.
            target = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)
            if error.errno not in (UC_ERR_FETCH_PROT, UC_ERR_FETCH_UNMAPPED) or target in instructions:
                raise

        new_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)
        next_pc = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)

        memory_accesses.append(list(step_accesses))
        after = read_all_registers_and_write_to_list(cpu_emulator)
        register_states.append(after)
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
        stack_states.append(
            read_stack(cpu_emulator, stack_cells, new_sp)
        )

        heap_states.append(heap.snapshot(cpu_emulator.mem_read))

        if (is_bl and not library_call) or is_blr:
            # The actual destination PC identifies the called function.
            labels = address_to_labels.get(next_pc, [])

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

        frame_states.append(snapshot_frames(new_sp))

        executed_addresses.append(PC)
        instruction_number.append(instruction_indices[PC])

        PC = next_pc
        counter += 1

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
    )

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

