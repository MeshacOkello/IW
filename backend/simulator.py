from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN 
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ, UC_MEM_WRITE
import unicorn.arm64_const as reg

# Keystone:  An assembler, produces machine code from assembly
# Unicorn: A CPU emulator, provides a simulated AArch64 CPU with registers and memory




# Convert assembly code to bytes using Keystone
def convert_assembly_to_byte(assembly_code):
    # Create Keystone assembler
    assembler = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    byte_code, statement_count = assembler.asm(assembly_code)

    return bytes(byte_code)

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


def run_byte_code(byte_code, address_to_labels=None):
    if address_to_labels is None:
        address_to_labels = {}

    # Create CPU emulator
    cpu_emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu_emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_NZCV, 0)

    # Allocate memory for instructions
    cpu_emulator.mem_map(0x1000, 4096)
    cpu_emulator.mem_write(0x1000, byte_code)

    # Allocate stack memory and initialize SP
    cpu_emulator.mem_map(0x8000, 4096)
    cpu_emulator.reg_write(reg.UC_ARM64_REG_SP, 0x9000)

    register_states = []
    executed_addresses = []

    return record_register_states(
        cpu_emulator,
        register_states,
        byte_code,
        executed_addresses,
        address_to_labels,
    )

# Stack memory mapped in run_byte_code: [STACK_START, STACK_END)
STACK_START = 0x8000
STACK_END = 0x9000

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
    register_states,
    byte_code,
    executed_addresses,
    address_to_labels,
):
    instruction_number = [None]
    stack_states = []
    stack_cells = []
    stack_writes = []
    memory_accesses = [[]]
    step_accesses = []

    def record_write(uc, access, address, size, value, user_data):
        stack_writes.append((address, size))

    def record_access(uc, access, address, size, value, user_data):
        step_accesses.append({
            'kind': 'write' if access == UC_MEM_WRITE else 'read',
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
    starting_address = 0x1000
    stopping_address = starting_address + len(byte_code)
    PC = starting_address

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
        and starting_address <= PC < stopping_address
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

        cpu_emulator.emu_start(
            PC,
            stopping_address,
            count=1,
        )

        new_sp = cpu_emulator.reg_read(reg.UC_ARM64_REG_SP)
        next_pc = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)

        memory_accesses.append(list(step_accesses))
        register_states.append(
            read_all_registers_and_write_to_list(cpu_emulator)
        )

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

        if is_bl or is_blr:
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
        instruction_number.append(
            (PC - starting_address) // 4 + 1
        )

        PC = next_pc
        counter += 1

    return (
        register_states,
        stack_states,
        executed_addresses,
        instruction_number,
        memory_accesses,
        frame_states,
    )

import re

def map_addresses_to_lines(assembly_code):
    address_to_line = {}
    address_to_labels = {}
    address = 0x1000

    for line_number, line in enumerate(assembly_code.splitlines(), start=1):
        instruction = line.split("//", 1)[0].strip()

        while True:
            label = re.match(r"^([\w.$]+):\s*", instruction)
            if not label:
                break

            label_name = label.group(1)
            address_to_labels.setdefault(address, []).append(label_name)

            instruction = instruction[label.end():].strip()

        if not instruction:
            continue

        address_to_line[address] = line_number
        address += 4

    return address_to_line, address_to_labels


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
    #print(convert_assembly_to_byte(assem))
    print(run_byte_code(convert_assembly_to_byte(assem)))

if __name__ == '__main__':
    main()

