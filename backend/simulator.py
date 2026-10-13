from keystone import Ks, KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN 
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
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


def run_byte_code(byte_code):
    # create CPU emulator
    cpu_emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)

    # Allocate memory space(starting address, size) 
    cpu_emulator.mem_map(0x1000, 4096)

    # Put the byte code into the memory allocated
    cpu_emulator.mem_write(0x1000, byte_code)

    # A snapshot list to store lists of snapshots, ie the ith list
    # holds the register state at the ith executed instruction

    register_states = [] # Each element is a list of size 34
    executed_addresses = [] # List showing which instruction was executed to produce register_states at i
    return record_register_states(cpu_emulator, register_states, byte_code, executed_addresses)
    
    

def read_all_registers_and_write_to_list(cpu_emulator):
    regs = []
    for i in range(31):
        register = (registers[f'x{i}'])
        regs.append(cpu_emulator.reg_read(register))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_SP))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_PC))
    regs.append(cpu_emulator.reg_read(reg.UC_ARM64_REG_NZCV))
    return regs



def record_register_states(cpu_emulator, register_states, byte_code, executed_addresses):
    instruction_number = []
    instruction_number.append(None)
    counter = 0
    # Limit to avoid infinite loops
    execution_limit = 10_000
    starting_address = 0x1000
    PC = 0x1000
    cpu_emulator.reg_write(reg.UC_ARM64_REG_PC, PC)
    register_states.append(read_all_registers_and_write_to_list(cpu_emulator))
    executed_addresses.append(None)

    while counter < execution_limit and PC < 0x1000 + len(byte_code):
        cpu_emulator.emu_start(PC, 0x1000 + len(byte_code), count=1)
        register_states.append(read_all_registers_and_write_to_list(cpu_emulator))
        executed_addresses.append(PC)
        PC = cpu_emulator.reg_read(reg.UC_ARM64_REG_PC)
        counter += 1
        instruction_number.append((executed_addresses[counter] - starting_address)//4+1)

    return (register_states, executed_addresses, instruction_number)   



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

