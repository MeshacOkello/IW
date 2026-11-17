# AArch64 Assembly Visualizer

An interactive tool for learning AArch64 assembly, designed around Princeton’s COS 217 course.

Write assembly, execute it one instruction at a time, and see how each instruction changes registers and memory. Step backward to revisit earlier states, inspect recursive function calls, and follow programs that allocate memory or interact with the user.

## Features

- **Execution controls:** Load, step forward and backward, reset, or run automatically with adjustable playback speed.
- **Code tracking:** Highlight the executed instruction and scroll to keep it visible.
- **Instruction explanations:** Explain the instruction alongside the state it produced.
- **Registers:** Inspect general-purpose registers, SP, PC, and condition flags, with changed values highlighted.
- **Stack frames:** Group stack memory by function call, including recursive calls.
- **Heap:** Visualize allocations and writes, and watch blocks disappear when freed.
- **Memory sections:** Inspect `.data`, `.bss`, and `.rodata`, including labels and stored contents.
- **Input and output:** Read input through a popup and view stdout alongside execution.
- **Display formats:** Choose hexadecimal or decimal representations for addresses and data.
- **Error reporting:** Say what failed and where, in plain language, with the source line and a suggested correction.

## Getting started

### Requirements

- Python 3
- Node.js and npm
- Flask, Keystone Engine, and Unicorn Engine

Install the backend dependencies:

```bash
python3 -m pip install flask keystone-engine unicorn
```

Install the frontend dependencies from the project root:

```bash
npm install
```

### Start the backend

From the project root:

```bash
cd backend
python3 -m flask --app app run --port 5001 --debug
```

### Start the frontend

In another terminal, from the project root:

```bash
npm run dev
```

Open the local URL printed by Vite.

## Using the visualizer

1. Enter an AArch64 assembly program in the editor.
2. Select **Load** to assemble it and generate its execution history.
3. Use **Next** and **Back** to inspect individual steps, or **Run** for automatic playback.
4. Inspect the highlighted instruction, explanation, registers, and memory.
5. When the program requests input, enter it in the popup to continue.

Registers, memory, and stdout reflect the selected step. **Reset** returns to the beginning of the recorded run. After editing the source, select **Load** again.

## Supported library functions

The visualizer simulates a small set of library functions:

| Purpose | Functions |
| --- | --- |
| Heap allocation | `malloc`, `free` |
| Output | `printf`, `puts`, `putchar` |
| Input | `getchar`, `fgets`, `scanf` |

`printf` supports literal text, `%%`, `%d`, `%u`, `%ld`, `%lu`, `%c`, `%s`, and `%p`.

`scanf` supports one `%d` or `%ld` conversion.

For `fgets`, pass the buffer address in `x0`, its size in `w1`, and `0` in `x2` to select simulated stdin.

These functions are simulated by the backend; the project does not load or execute a full C standard library.

## How it works

The frontend sends assembly source to a Python backend.

- **Keystone** assembles instructions into machine code.
- **Unicorn** executes ordinary machine instructions.
- **Python** manages memory, records execution states, and handles supported library calls.
- **React** displays the recorded states and provides playback controls.

Memory is divided into text, stack, heap, and static data sections. Section permissions prevent writes to read-only memory.

When input is needed, history generation pauses. After input arrives, the backend reconstructs execution using the saved source and input events, and the frontend extends the existing history.

## Error reporting

Every failure is answered with JSON that names the kind of problem, so the panel can say whose problem it is:

| Kind | Meaning |
| --- | --- |
| `assembly` | The program could not be turned into machine code. |
| `unsupported` | Valid AArch64 that the simulator does not simulate. |
| `runtime` | The program assembled, then failed while executing. |
| `request` | The frontend sent something the endpoint cannot accept. |
| `internal` | A bug in the simulator, never the program. |

An error carries the line number, that line's source text and a plain-language message. Advice is
added only when it is derived from the error's own facts: a near-miss name, the faulting address, the
specific rule broken. A generic checklist of things to look at is not an explanation, so a message the
simulator cannot add anything certain to stands on its own. The underlying assembler or CPU code is
kept in the payload but not shown for an error in the program, where it is noise next to a sentence
that already says what is wrong; for a failure of the tool itself it is the only clue, so it stays.
Addresses travel as data rather than text, so they follow the hexadecimal or decimal setting like
every other number.

Keystone reports a failure for a whole section, so the backend re-assembles the section one statement
at a time to find the line responsible. A misspelling is matched against the instructions the
simulator covers, preferring a transposition, so `mvo` suggests `mov`.

A run that fails partway still returns every step recorded before the fault. The failing step is
selected, and **Back** steps through the states that led to it. A failed run never prevents loading
another program.

Unexpected exceptions are logged on the server with their traceback and reported to the user as a
short note saying the program was not the cause. Explanations are commentary, so a failure to
explain a step serves the trace without explanations rather than discarding the run.

Some inputs used to take the backend down rather than raise an error, and are now reported instead:

- Source that Keystone's parser never returns from, in native code no signal or thread can
  interrupt. The shapes we know about are rejected before any source reaches the assembler, each
  naming its line: an unterminated `"` string, an unterminated `'` character literal, an unclosed
  `/*` comment, and a directive whose argument list has a hole in it (`.word 1, ,`, `.word ,1`,
  `.equ A, 1,`). For the rest, assembly runs in a worker process; a worker that stops answering is
  killed and replaced, so a hang costs one worker rather than the backend. The worker is reused, so
  it is started once (~75 ms) and adds about a millisecond per load after that. Set
  `ASSEMBLY_TIMEOUT` to change the 5-second limit.
- A call that never returns. Each recorded step snapshots every live call, so an uncapped depth grew
  the trace with the square of the step count. Recursion stops at 256 frames with an error that keeps
  every step already recorded.

## Scope and limitations

This is an educational assembly simulator, with support focused on the COS 217 instruction set and examples. It is not a complete operating system or a general-purpose AArch64 environment.

- Assembly input only.
- Limited library support; no file I/O or arbitrary external functions.
- No floating-point formatting or full `printf`/`scanf` syntax.
- Execution is limited to 10,000 instruction steps.
- The simulated heap is 16 KiB.
- Input and output each have a 1 MiB limit.
- Strings and input/output operate on UTF-8 bytes.
- Memory checks detect several invalid accesses but cannot identify every pointer or buffer error.
- Recursion is limited to 256 nested calls.

## Development checks

Run backend tests from the project root:

```bash
python3 -B -m unittest discover -s backend
```

Run frontend tests and checks:

```bash
node --test src/*.test.js
npm run lint
npm run build
```

On Apple Silicon Macs, Keystone may require the Homebrew library path:

```bash
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/keystone/lib
```

## Project context

Developed as a Princeton independent work project to help students connect AArch64 instructions with changes in registers, memory, and function calls.
