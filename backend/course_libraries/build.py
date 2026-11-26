"""Compile the bundled course code into assembly the simulator can load.

    python3 course_libraries/build.py

Run it after changing any C source here. It needs clang (any recent one: the
target is cross-compiled, nothing is linked) and writes one `<bundle>.s` per
bundle next to this file. The simulator never runs clang; it reads those
generated files, which are checked in.

Each C file is compiled on its own, as gcc217 would compile it, at -O1 (the
assignment's "-O" build) so it keeps values in callee-saved registers across
calls the way real compiled callers do. The tiny code model makes every
address a plain `adr`, which Keystone encodes reliably.

The output is rewritten into one flat image: code first, then constants and
data, with each file's local labels renamed so files cannot collide. Lines
the loader reads:

    .globl NAME     a function other code may call
    .import NAME    a function this bundle calls but does not define; the
                    linker fills it from the program or the simulator's
                    library
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIBC = os.path.join(HERE, 'libc')

# Each bundle: its C sources, in link order. libc.c is added to every one.
BUNDLES = {
    'bigint': ['bigint/fib.c', 'bigint/bigint.c'],
}

FLAGS = [
    '-target', 'aarch64-linux-gnu', '-O1', '-mcmodel=tiny', '-fno-pic',
    '-ffreestanding', '-fno-builtin', '-fno-jump-tables', '-fno-stack-protector',
    '-fno-asynchronous-unwind-tables', '-fno-unwind-tables', '-fno-common',
    '-nostdlibinc', '-w', '-S', '-o', '-',
]

DROPPED = ('.file', '.ident', '.addrsig', '.addrsig_sym', '.type', '.size', '.local')
LOCAL_LABEL = re.compile(r'\.L[\w.$]+')
SECTION = re.compile(r'^\s*(?:\.section\s+([^,\s]+)|(\.text|\.data|\.bss|\.rodata))\b')
COMMON = re.compile(r'^\s*\.comm\s+([\w.$]+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?')


def compile_file(path):
    # Compiled from its own directory by bare name, so __FILE__ in an
    # assertion message reads "bigint.c", as it does on armlab.
    command = ['clang', *FLAGS, '-isystem', resource_include(), '-I', os.path.join(LIBC, 'include'),
               os.path.basename(path)]
    return subprocess.run(command, check=True, capture_output=True, text=True,
                          cwd=os.path.dirname(path)).stdout


def resource_include():
    directory = subprocess.run(['clang', '-print-resource-dir'], check=True,
                               capture_output=True, text=True).stdout.strip()
    return os.path.join(directory, 'include')


def kind_of(section):
    if section.startswith('.text'):
        return 'text'
    if section.startswith('.note'):
        return None
    if section.startswith(('.bss', '.tbss')):
        return 'bss'
    if section.startswith('.rodata'):
        return 'rodata'
    return 'data'


def clean(assembly, prefix):
    """Split one file's assembly into its text, rodata, data and bss lines."""
    parts = {'text': [], 'rodata': [], 'data': [], 'bss': []}
    globals_, defined, called = set(), set(), set()
    current = 'text'
    for line in assembly.splitlines():
        line = line.split('//', 1)[0].rstrip()
        if not line.strip():
            continue
        line = LOCAL_LABEL.sub(lambda match: f'.L{prefix}_{match[0][2:]}', line)
        stripped = line.strip()
        section = SECTION.match(line)
        if section:
            current = kind_of(section[1] or section[2])
            continue
        head = stripped.split(None, 1)[0]
        if head in DROPPED:
            continue
        if head in ('.globl', '.global'):
            globals_.add(stripped.split(None, 1)[1].strip())
            continue
        common = COMMON.match(line)
        if common:
            name, size, alignment = common[1], int(common[2]), int(common[3] or 8)
            parts['bss'].extend([f'.p2align {alignment.bit_length() - 1}', f'{name}:',
                                 f'.zero {size}'])
            defined.add(name)
            continue
        if current is None:
            continue
        if stripped.endswith(':'):
            defined.add(stripped[:-1])
        if head in ('bl', 'b'):
            target = stripped.split(None, 1)[1].strip()
            if not target.startswith('.L'):
                called.add(target)
        parts[current].append(line)
    return parts, globals_, defined, called


def build(name, sources):
    paths = [os.path.join(HERE, source) for source in sources] + [os.path.join(LIBC, 'libc.c')]
    combined = {'text': [], 'rodata': [], 'data': [], 'bss': []}
    exports, defined, called = set(), set(), set()
    for index, path in enumerate(paths):
        parts, globals_, names, calls = clean(compile_file(path), f'f{index}')
        for kind, lines in parts.items():
            combined[kind].extend(lines)
        exports |= globals_
        defined |= names
        called |= calls
    imports = sorted(called - defined)
    # The bundle's own C library helpers are internal, not part of the
    # course code's interface.
    exports = sorted(name for name in exports if not name.startswith('__') and name != 'main') + (
        ['main'] if 'main' in exports else [])

    header = [
        f'// Generated by course_libraries/build.py from {", ".join(sources)} and libc/libc.c.',
        '// Do not edit by hand: change the C sources and run the script again.',
    ]
    body = [f'.globl {symbol}' for symbol in exports] + [f'.import {symbol}' for symbol in imports]
    for kind in ('text', 'rodata', 'data', 'bss'):
        if combined[kind]:
            body.append(f'// {kind}')
            body.append('.p2align 4')
            body.extend(combined[kind])
    with open(os.path.join(HERE, f'{name}.s'), 'w') as output:
        output.write('\n'.join(header + body) + '\n')
    print(f'{name}.s: exports {", ".join(exports)}; imports {", ".join(imports)}')


def main():
    for name, sources in BUNDLES.items():
        build(name, sources)


if __name__ == '__main__':
    sys.exit(main())
