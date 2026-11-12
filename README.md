# AArch64 Assembly Visualizer

The visualizer assembles with Keystone, runs instructions with Unicorn, and replays recorded registers, memory, source lines, explanations, and stdout. Input uses deterministic replay of the saved source, execution limit, and recorded submissions. Back, Next, Reset, and Run use that history. Loading starts a fresh run. Source edits require Load before execution can continue.

## Limited library simulation

Supported direct `bl` calls are intercepted in Python and each completed call counts as one instruction step. This is a limited simulation of these library functions. The target uses LP64/AAPCS64, with 32-bit `int`, 64-bit `long` and pointers, arguments in x0–x7, and subsequent `printf` arguments in 8-byte slots at SP.

| Function | Supported behavior |
| --- | --- |
| `printf` | Literal text, `%%`, `%d`, `%u`, `%ld`, `%lu`, `%c`, `%s`, `%p`. Returns the number of output bytes in w0. `%p` prints `0x` followed by lowercase hex, including `0x0` for null. |
| `puts` | Reads a null-terminated string, adds a newline, returns 0 as its nonnegative success result. |
| `putchar` | Outputs the low byte of its int argument and returns that unsigned byte in w0. |
| `getchar` | Consumes one buffered byte, or returns EOF as `w0 = 0xffffffff` after explicit EOF. |
| `fgets` | x0 is the destination, w1 is its size, x2 must be 0 for simulated stdin. Reads at most size−1 bytes, retains a consumed newline, and writes a terminating zero. Returns the destination, or null on EOF before any bytes. Size 1 writes only the terminator and succeeds without consuming input. Other sizes must be from 1 through 65536. |
| `scanf` | Exactly one `%d` or `%ld`, with optional surrounding whitespace. Writes 4 or 8 bytes and returns 1 on success, 0 on matching failure, or EOF before a conversion. The first nonmatching character remains buffered, except a consumed optional sign. Out-of-range integer input is an explicit simulation error. Trailing whitespace in the format waits for a non-whitespace byte or EOF. |
| `malloc`, `free` | Aligned allocation in the dedicated simulated heap, reuse, and the existing allocation/access checks. |

Students can define functions with these names to override interception. Unsupported conversions and modifiers, other library functions, other streams, and `gets` are rejected. Widths, precision, flags, floating-point formats, suppressed assignments, and additional scanf conversions are unsupported.

### UTF-8 and buffering

Submit sends the textarea text encoded as UTF-8 without adding a newline, then marks stdin as EOF. Empty Submit sends EOF immediately. Embedded newlines are preserved. Unused bytes remain buffered for later calls. Closing the dialog submits nothing. EOF takes effect after all buffered bytes have been consumed and is distinct from input that has not arrived yet. The compact modal uses the last output line ending in a colon, question mark, or chevron since the previous completed input call as its title. Otherwise its title is Input. Stdout retains the complete output.

Strings and streams contain bytes. `getchar`, `putchar`, `%c`, and the size limit of `fgets` operate on bytes and may split a UTF-8 sequence. Stdout decodes the bytes recorded up to the selected step as UTF-8, replacing incomplete or invalid sequences with the replacement character. A later step can complete an earlier split sequence. Format strings use ASCII conversion syntax and may contain UTF-8 literal text. Stdout displays text with spaces and newlines preserved. Its text is the program output, so global number-format controls do not rewrite it.

### Memory and execution limits

Intercepted reads and writes use actual Unicorn memory. They validate section bounds and heap allocations, preserve read-only `.text` and `.rodata`, explicitly record memory accesses, and update heap initialization, Stack, and section history. String reads require a zero terminator within 65536 bytes. Individual formatted output and fgets sizes are limited to 65536 bytes. Total input and output each have a 1 MiB limit. The instruction limit defaults to 10000.

The allocator's existing limits apply. Address checks cannot distinguish a stale pointer from a fresh allocation at the same address, or infer the intended buffer object within a data section. Uninitialized memory reads observe Unicorn's bytes. File streams, locale rules, errno, and full libc behavior are outside this simulation.

## Input and history API

`POST /simulate` accepts `assembly_code`, optional `execution_limit` (1–10000), and `input_events` (initially an empty list). The response contains a `status` whose state is `completed`, `waiting`, `execution_limit`, or `error`. Runtime errors include the successful execution prefix and use HTTP 400. Assembly and invalid-request errors also use HTTP 400.

A waiting status identifies the pending function, source line, PC, completed step count, execution occurrence, and `request_id`. The pending call has not completed and has no snapshot yet. Continue by resubmitting the same source and settings with the previous events plus either `{"request_id":"…","text":"42"}` or `{"request_id":"…","text":"42","eof":true}`. An EOF submission may omit text for compatibility with empty EOF events. Each ID belongs to that particular waiting request. Repeated calls inside a loop have different occurrences. A single call may need several submissions, for example scanf consuming whitespace. Duplicate, stale, and unused submissions are rejected.

Stdout is recorded as byte chunks under `stdout.chunks`, with `stdout_states[step]` giving the chunk count visible at that step. Continuation regenerates history, and the frontend verifies the entire earlier snapshot prefix and memory/output version tables before extending it. It retains the earlier snapshots. Failed requests leave the current trace and recorded submissions available for retry. Displayed output is derived from the selected step, so replay adds no duplicate output.

## Checks

With Flask, keystone-engine, and Unicorn installed, run `python -B -m unittest discover -s backend`. On this Mac, the Keystone Python binding uses the Homebrew native library with `DYLD_LIBRARY_PATH=/opt/homebrew/opt/keystone/lib`. The backend must run in an environment that permits Unicorn to initialize.

Frontend checks are `node --test src/history.test.js`, `npm run lint`, and `npm run build`.
