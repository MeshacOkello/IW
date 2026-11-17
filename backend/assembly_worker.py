"""Run Keystone where a hang cannot take the backend with it.

Keystone's parser does not return on several malformed inputs: an unterminated
string or character literal, an unclosed comment, a directive argument list
with a hole in it, an incomplete numeric literal. The loop is in native code,
so no signal, thread or `faulthandler` can interrupt it in process.

assembler.py rejects the shapes we know about, with a message naming the line.
This module is the backstop for the ones we do not: assembly runs in a child
process, and a child that stops answering is killed and replaced. The student
gets an error, and the next program still loads.
"""
import logging
import os
import queue
import subprocess
import sys
import threading

from assembly_child import read_message, write_message
from errors import ASSEMBLY, payload

logger = logging.getLogger(__name__)

CHILD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assembly_child.py')
# Generous next to a normal assemble, which takes milliseconds. Only source
# Keystone cannot finish ever reaches it.
ASSEMBLY_TIMEOUT = float(os.environ.get('ASSEMBLY_TIMEOUT', '5'))

_worker = None
_lock = threading.Lock()


class AssemblyTimeout(Exception):
    """Keystone did not finish with this source."""


class _Worker:
    """A child process that assembles, with its replies read off a thread.

    subprocess rather than multiprocessing: spawning a multiprocessing child
    re-imports the parent's __main__, which fails unless the entry script
    guards it. A plain script has no such requirement, however the backend
    was started.
    """

    def __init__(self):
        self.process = subprocess.Popen(
            [sys.executable, '-B', CHILD],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            # Inherit stderr so a child that cannot start says why.
            cwd=os.path.dirname(CHILD),
        )
        self.replies = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                message = read_message(self.process.stdout)
                if message is None:
                    break
                self.replies.put(message)
        except (OSError, ValueError, EOFError):
            pass
        finally:
            self.replies.put(None)   # the child is gone

    def alive(self):
        return self.process.poll() is None

    def ask(self, source, timeout):
        write_message(self.process.stdin, source)
        reply = self.replies.get(timeout=timeout)
        if reply is None:
            raise EOFError('the assembly worker exited')
        return reply

    def stop(self):
        try:
            self.process.kill()
        except OSError:
            pass
        self.process.wait(timeout=5)
        # The reader thread ends on EOF; closing both pipes releases them.
        for pipe in (self.process.stdin, self.process.stdout):
            try:
                pipe.close()
            except OSError:
                pass


def assemble_in_worker(source, timeout=None):
    """Assemble in the child process, or raise AssemblyTimeout.

    Raises the same AssemblyError the in-process assembler would, so a caller
    cannot tell the difference for source that assembles or fails normally.
    """
    from assembler import AssemblyError

    global _worker
    timeout = ASSEMBLY_TIMEOUT if timeout is None else timeout
    with _lock:
        if _worker is None or not _worker.alive():
            _worker = _Worker()
        worker = _worker
        try:
            outcome, result = worker.ask(source, timeout)
        except (queue.Empty, EOFError, OSError) as error:
            # Either the child is stuck inside Keystone or it died. Replace it,
            # so the next program is assembled by a healthy process.
            logger.error('Assembly did not finish within %ss (%s); replacing the worker',
                         timeout, type(error).__name__)
            worker.stop()
            _worker = None
            raise AssemblyTimeout(timeout) from None

    if outcome == 'program':
        return result
    if outcome == 'assembly_error':
        raise AssemblyError(
            result['message'], line=result['line'], context=result['context'],
            kind=result['kind'], suggestion=result['suggestion'], detail=result['detail'],
        )
    raise RuntimeError(f'assembly worker failed: {result}')


def timeout_error(timeout=None):
    """The error shown when the assembler could not finish."""
    timeout = ASSEMBLY_TIMEOUT if timeout is None else timeout
    return payload(
        ASSEMBLY,
        'The assembler could not finish with this source and was stopped after '
        f'{timeout:g} seconds.',
        suggestion='Something in the program puts the assembler into a loop. Look for an '
                   'unclosed quote or comment, a stray comma, or an incomplete number, '
                   'and load a smaller part of the program to find it.',
        detail='assembler timeout',
    )


def shutdown():
    """Stop the worker, for tests and for a clean exit."""
    global _worker
    with _lock:
        if _worker is not None:
            _worker.stop()
            _worker = None
