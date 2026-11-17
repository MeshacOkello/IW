"""The child half of the assembly worker. Run as a script, never imported.

Reads a length-prefixed pickled source string on stdin and writes a
length-prefixed pickled (outcome, payload) pair on stdout, until stdin closes.
Keeping this a plain script, started with subprocess, means it does not care
how the parent process was started.
"""
import os
import pickle
import struct
import sys

HEADER = struct.Struct('!I')


def read_message(stream):
    header = stream.read(HEADER.size)
    if len(header) < HEADER.size:
        return None
    size, = HEADER.unpack(header)
    body = stream.read(size)
    if len(body) < size:
        return None
    return pickle.loads(body)


def write_message(stream, message):
    body = pickle.dumps(message, protocol=pickle.HIGHEST_PROTOCOL)
    stream.write(HEADER.pack(len(body)) + body)
    stream.flush()


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from assembler import AssemblyError, assemble_program

    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    while True:
        source = read_message(stdin)
        if source is None:
            return
        try:
            write_message(stdout, ('program', assemble_program(source)))
        except AssemblyError as error:
            write_message(stdout, ('assembly_error', {
                'message': error.message, 'line': error.line, 'context': error.context,
                'kind': error.kind, 'suggestion': error.suggestion, 'detail': error.detail,
            }))
        except BaseException as error:  # noqa: BLE001 - reported as an internal failure
            write_message(stdout, ('internal_error', f'{type(error).__name__}: {error}'))


if __name__ == '__main__':
    main()
