"""Link a program against the bundled course code, as gcc217 would.

A COS 217 assignment often gives students C files and asks for one function
in assembly: Assignment 5 gives fib.c and bigint.c and asks for BigInt_add.
On armlab the student runs `gcc217 fib.c bigint.c bigintadd.s`. Here the
student only loads their .s file, so the linker supplies the rest.

A bundle (see course_libraries/build.py) is the course's C code compiled to
ARM64 once and checked in as assembly. It is linked into a run when the
program leaves something undefined that the bundle defines:

- the program calls one of the bundle's functions, such as BigInt_new; or
- the program has no main, and the bundle's main can run with it: everything
  the bundle needs is defined by the program or the simulator's library.
  bigintadd.s has no main but defines BigInt_add, so fib.c's main runs it.

Otherwise nothing is linked and the program runs exactly as before. Bundled
code never appears in the editor or the trace: it runs between the
program's own steps, as a library function does.
"""
import functools
import os
import re
from dataclasses import dataclass, field

from keystone import KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN, Ks

from heap import LIBRARY_SYMBOLS

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIRECTORY = os.path.join(HERE, 'course_libraries')
BUNDLE_NAMES = ('bigint',)

PAGE_SIZE = 0x1000
# Bundles sit far from everything a program can map: its sections, the stack,
# the heap and the library call addresses.
BUNDLE_BASE = 0x600000
BUNDLE_SPACING = 0x100000

# A larger heap for linked runs. A BigInt object alone is 256 KiB.
LINKED_HEAP_START = 0x1000000
LINKED_HEAP_SIZE = 0x400000

# The library call addresses stay unmapped. In a linked run a fetch there is
# a library call made by bundled code; past them is a trap for each import
# nothing defined, and the address main returns to.
LIBRARY_BASE = min(LIBRARY_SYMBOLS.values())
UNRESOLVED_BASE = LIBRARY_BASE + 0x800
EXIT_ADDRESS = LIBRARY_BASE + 0xff0

IDENTIFIER = re.compile(r'(?<![\w.$])[A-Za-z_.$][\w.$]*', re.ASCII)


@dataclass(frozen=True)
class Bundle:
    name: str
    base: int
    image: bytes
    exports: dict          # function name -> address
    imports: tuple         # names the bundle needs from outside
    slots: dict            # import name -> address of its 8-byte target
    unresolved: dict       # trap address -> import name
    symbols: dict = field(default_factory=dict)  # every label, for loading

    @property
    def end(self):
        return self.base + len(self.image)

    @property
    def mapped_size(self):
        return (len(self.image) + PAGE_SIZE - 1) // PAGE_SIZE * PAGE_SIZE

    def needs_from_program(self):
        return [name for name in self.imports if name not in LIBRARY_SYMBOLS]


def read_bundle_source(name):
    with open(os.path.join(BUNDLE_DIRECTORY, f'{name}.s')) as source:
        return source.read()


def assemble_bundle(name, base):
    """Assemble one bundle at its fixed address.

    Its calls into the program go through a stub per import, the way a
    shared library's calls go through its PLT: load the target from a slot,
    then branch. The slot is filled at link time, so the image itself does
    not depend on the program.
    """
    exports, imports, body = [], [], []
    for line in read_bundle_source(name).splitlines():
        stripped = line.strip()
        if stripped.startswith('//') or not stripped:
            continue
        head, _, rest = stripped.partition(' ')
        if head == '.globl':
            exports.append(rest.strip())
        elif head == '.import':
            imports.append(rest.strip())
        else:
            body.append(line)

    lines = []
    for import_name in imports:
        if import_name in LIBRARY_SYMBOLS:
            lines.append(f'.equ {import_name}, {LIBRARY_SYMBOLS[import_name]}')
    unresolved = {}
    stubs = ['.p2align 3']
    program_imports = [name for name in imports if name not in LIBRARY_SYMBOLS]
    for index, import_name in enumerate(program_imports):
        trap = UNRESOLVED_BASE + 4 * index
        unresolved[trap] = import_name
        stubs += [f'{import_name}:', f'ldr x16, .Lslot_{index}', 'br x16',
                  f'.Lslot_{index}:', f'.xword {trap}']
    labels = sorted({line.strip()[:-1] for line in body
                     if line.strip().endswith(':') and not line.strip().startswith('.L')})
    markers = labels + [f'.Lslot_{index}' for index in range(len(program_imports))]
    table = ['.p2align 3', '.Lmarker_table:'] + [f'.xword {marker}' for marker in markers]
    source = '\n'.join(lines + body + stubs + table)

    assembler = Ks(KS_ARCH_ARM64, KS_MODE_LITTLE_ENDIAN)
    output, _ = assembler.asm(source, addr=base, as_bytes=True)
    if not output:
        raise RuntimeError(f'bundle {name} assembled to nothing')
    size = len(output) - 8 * len(markers)
    values = [int.from_bytes(output[offset:offset + 8], 'little')
              for offset in range(size, len(output), 8)]
    addresses = dict(zip(markers, values))
    return Bundle(
        name=name, base=base, image=bytes(output[:size]),
        exports={symbol: addresses[symbol] for symbol in exports},
        imports=tuple(imports),
        slots={import_name: addresses[f'.Lslot_{index}']
               for index, import_name in enumerate(program_imports)},
        unresolved=unresolved,
        symbols={label: addresses[label] for label in labels},
    )


@functools.cache
def bundles():
    return tuple(assemble_bundle(name, BUNDLE_BASE + index * BUNDLE_SPACING)
                 for index, name in enumerate(BUNDLE_NAMES))


def exported_functions():
    """Every bundled function a program may call by name, except main."""
    functions = {}
    for bundle in bundles():
        for name, address in bundle.exports.items():
            if name != 'main':
                functions.setdefault(name, address)
    return functions


@dataclass
class Link:
    bundles: tuple
    entry: int | None            # the bundle's main, when it runs the program
    slot_targets: dict           # slot address -> program function address

    def contains(self, address):
        return any(bundle.base <= address < bundle.end for bundle in self.bundles)

    def unresolved_name(self, address):
        for bundle in self.bundles:
            if address in bundle.unresolved:
                return bundle.unresolved[address]
        return None

    def function_at(self, address):
        for bundle in self.bundles:
            for name, value in bundle.exports.items():
                if value == address:
                    return name
        return None


def referenced_names(program):
    names = set()
    for statement in program.instructions.values():
        parts = statement.text.split(None, 1)
        if len(parts) == 2:
            names.update(IDENTIFIER.findall(parts[1]))
    return names


def link(program):
    """The bundles this program needs, or None when it needs none."""
    defined = set(program.symbols)
    functions = {name for name, address in program.symbols.items()
                 if address in program.instructions}
    referenced = referenced_names(program) - defined
    chosen, entry = [], None
    for bundle in bundles():
        calls_bundle = bool(referenced & (set(bundle.exports) - {'main'}))
        runs_program = (
            entry is None and 'main' not in defined and 'main' in bundle.exports
            and bundle.needs_from_program()
            and all(name in functions for name in bundle.needs_from_program())
        )
        if runs_program:
            entry = bundle.exports['main']
        if calls_bundle or runs_program:
            chosen.append(bundle)
    if not chosen:
        return None
    slot_targets = {}
    for bundle in chosen:
        for name, slot in bundle.slots.items():
            if name in functions:
                slot_targets[slot] = program.symbols[name]
    return Link(tuple(chosen), entry, slot_targets)


# The command line each bundle's main is run with. Assignment 5's fib reads
# the Fibonacci index from argv[1].
BUNDLE_ARGUMENTS = {
    'bigint': ('./fib', '100'),
}
