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
        objective: "See how each instruction changes one register.",
        source: arithmetic,
        expected: [
            { code: "x3 = 25" }, { code: "x4 = 15" }, { code: "x5 = 125" },
            { text: "Status: Execution complete. main returned 0." },
        ],
    },
    loop: {
        id: "loop",
        title: "A counting loop",
        objective: "Watch cmp set the flags and ble decide whether to loop again.",
        source: loop,
        expected: [
            { code: "x0 = 15" },
            { text: "ble jumps back four times, then falls through on the fifth pass." },
        ],
    },
    array: {
        id: "array",
        title: "Arrays and pointers",
        objective: "Follow a pointer through an array in .data.",
        source: array,
        expected: [
            { text: "x1 moves 8 bytes per pass." },
            { code: "total = 9" },
            { text: "The total row in .data is highlighted when it is written." },
        ],
    },
    recursion: {
        id: "recursion",
        title: "Recursion and stack frames",
        objective: "See every call get its own frame, and each return remove one.",
        source: recursion,
        expected: [
            { text: "Four fact frames stack above main, then unwind." },
            { text: "Status: main returned 24." },
        ],
    },
    malloc: {
        id: "malloc",
        title: "malloc and free",
        objective: "Watch a heap block appear, fill up and disappear.",
        source: malloc,
        expected: [
            { text: "A 16-byte block appears in Heap, then fills with 42 and 7." },
            { text: "After free: No active allocations." },
        ],
    },
    greeting: {
        id: "greeting",
        title: "Read a line, print a line",
        objective: "Answer an input box and see the reply in Stdout.",
        source: greeting,
        expected: [
            { text: "Type" }, { code: "Ada" }, { text: "and select Submit. Stdout shows:" },
            { code: "What is your name? Hello, Ada!" },
        ],
    },
    nullPointer: {
        id: "null-pointer",
        title: "A null pointer",
        objective: "Find the cause of a runtime error by stepping back.",
        source: nullPointer,
        intentionalError: true,
        expected: [
            { text: "Runtime error on line 8. The two steps before it stay recorded, and" },
            { code: "x0 = 0" },
            { text: "shows why the load failed." },
        ],
    },
};
