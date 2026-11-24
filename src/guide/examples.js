// The runnable programs on the How to use page. Each source file is run by
// backend/test_guide_examples.py, which checks the result promised here.
import arithmetic from "./examples/arithmetic.s?raw";
import loop from "./examples/loop.s?raw";
import array from "./examples/array.s?raw";
import recursion from "./examples/recursion.s?raw";
import malloc from "./examples/malloc.s?raw";
import greeting from "./examples/greeting.s?raw";
import nullPointer from "./examples/null-pointer.s?raw";

export const EXAMPLES = {
    arithmetic: {
        id: "arithmetic",
        title: "Arithmetic",
        objective: "Compute a sum, difference, and product.",
        source: arithmetic,
        expected: [
            { code: "x3 = 25" }, { code: "x4 = 15" }, { code: "x5 = 125" },
            { text: "Status: Execution complete. main returned 0." },
        ],
    },
    loop: {
        id: "loop",
        title: "A counting loop",
        objective: "Sum the integers 1 through 5 using cmp and ble.",
        source: loop,
        expected: [
            { code: "x0 = 15" },
            { text: "ble jumps back four times, then falls through on the fifth pass." },
        ],
    },
    array: {
        id: "array",
        title: "Arrays and pointers",
        objective: "Add four 8-byte values and store their sum in total.",
        source: array,
        excerpt: "    adr     x1, array\n    mov     x2, 4\n    mov     x0, 0\nsumLoop:\n    ldr     x3, [x1], 8\n    add     x0, x0, x3\n    sub     x2, x2, 1\n    cbnz    x2, sumLoop",
        expected: [
            { text: "x1 moves 8 bytes per pass." },
            { code: "total = 9" },
            { text: "The total row in .data is highlighted when it is written." },
        ],
    },
    recursion: {
        id: "recursion",
        title: "Recursion and stack frames",
        objective: "Compute 4! with a 16-byte stack frame for each call.",
        source: recursion,
        excerpt: "fact:\n    sub     sp, sp, FACT_STACK_BYTECOUNT\n    str     x30, [sp]\n    str     x0, [sp, LN]\n    cmp     x0, 1\n    bgt     factRecurse\n    mov     x0, 1\n    b       factReturn",
        expected: [
            { text: "Four fact frames stack above main, then unwind." },
            { text: "Status: main returned 24." },
        ],
    },
    malloc: {
        id: "malloc",
        title: "malloc and free",
        objective: "Reserve 16 bytes, store two values, then release the allocation.",
        source: malloc,
        excerpt: "    mov     x0, 16\n    bl      malloc\n    mov     x1, 42\n    str     x1, [x0]\n    mov     x1, 7\n    str     x1, [x0, 8]\n    bl      free",
        expected: [
            { text: "A 16-byte block appears in Heap, then fills with 42 and 7." },
            { text: "After free: No active allocations." },
        ],
    },
    greeting: {
        id: "greeting",
        title: "Read a line, print a line",
        objective: "Read a name with fgets and print a greeting with printf.",
        source: greeting,
        excerpt: "    adr     x0, name\n    mov     x1, NAME_LENGTH\n    mov     x2, 0\n    bl      fgets\n    adr     x0, greetingStr\n    adr     x1, name\n    bl      printf",
        expected: [
            { text: "Type" }, { code: "Ada" }, { text: "and select Submit. Stdout shows:" },
            { code: "What is your name? Hello, Ada!" },
        ],
    },
    nullPointer: {
        id: "null-pointer",
        title: "A null pointer",
        objective: "Load from address 0 to produce a runtime error.",
        source: nullPointer,
        intentionalError: true,
        expected: [
            { text: "Runtime error on line 8. The two steps before it stay recorded, and" },
            { code: "x0 = 0" },
            { text: "shows why the load failed." },
        ],
    },
};
