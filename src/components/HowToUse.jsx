import { useEffect, useRef, useState } from "react";
import CodeExample from "./CodeExample";
import ReplaceCodeDialog from "./ReplaceCodeDialog";
import Icon from "./Icon";
import { EXAMPLES } from "../guide/examples";
import { SECTIONS } from "../guide/sections";
import "../guide/guide.css";

function Section({ id, title, children }) {
    return <section className="guide-section" id={id} aria-labelledby={`${id}-heading`}>
        <h2 id={`${id}-heading`} tabIndex={-1}>{title}</h2>
        {children}
    </section>;
}

function ReferenceTable({ headings, rows }) {
    return <div className="reference-table"><table>
        <thead><tr>{headings.map(heading => <th key={heading} scope="col">{heading}</th>)}</tr></thead>
        <tbody>{rows.map(([term, description], index) => <tr key={index}>
            <th scope="row">{term}</th><td>{description}</td>
        </tr>)}</tbody>
    </table></div>;
}

function scrollToSection(id, { focus = true } = {}) {
    const heading = document.getElementById(`${id}-heading`);
    if (!heading) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    heading.closest("section").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    // Moving focus with the scroll keeps keyboard and screen reader users in
    // the section they chose rather than back at the link.
    if (focus) heading.focus({ preventScroll: true });
}

export default function HowToUse({ section, hasUnsavedCode, onOpenExample }) {
    const [active, setActive] = useState(section ?? SECTIONS[0].id);
    const [pending, setPending] = useState(null);
    const opener = useRef(null);
    const sectionList = useRef(null);

    // Arriving at a section link, from the address bar or the browser history.
    useEffect(() => {
        if (section) scrollToSection(section, { focus: false });
        else window.scrollTo(0, 0);
    }, [section]);

    // Mark the section being read in the side navigation.
    useEffect(() => {
        const visible = new Map();
        const observer = new IntersectionObserver((entries) => {
            for (const entry of entries) visible.set(entry.target.id, entry.isIntersecting);
            const current = SECTIONS.find(({ id }) => visible.get(id));
            if (current) setActive(current.id);
        }, { rootMargin: "-15% 0px -70% 0px" });
        for (const { id } of SECTIONS) {
            const element = document.getElementById(id);
            if (element) observer.observe(element);
        }
        return () => observer.disconnect();
    }, []);

    // On a narrow screen the links are one scrolling strip: keep the current
    // one in view. Only the strip scrolls, never the page.
    useEffect(() => {
        const list = sectionList.current;
        const link = list?.querySelector("[aria-current]");
        if (!link || list.scrollWidth <= list.clientWidth) return;
        const offset = link.getBoundingClientRect().left - list.getBoundingClientRect().left;
        list.scrollLeft += offset - (list.clientWidth - link.offsetWidth) / 2;
    }, [active]);

    function goTo(event, id) {
        event.preventDefault();
        history.replaceState(null, "", `#/how-to/${id}`);
        setActive(id);
        scrollToSection(id);
    }

    function requestOpen(example, button) {
        opener.current = button;
        if (hasUnsavedCode(example.source)) setPending(example);
        else onOpenExample(example);
    }

    const ex = EXAMPLES;

    return (
        <div className="guide-page">
            <div className="guide-layout">
                <aside className="guide-sidebar">
                    <nav aria-label="On this page">
                        <p className="sidebar-title" aria-hidden="true">On this page</p>
                        <ol ref={sectionList}>
                            {SECTIONS.map(({ id, title }) => (
                                <li key={id}>
                                    <a href={`#/how-to/${id}`} onClick={(event) => goTo(event, id)}
                                        aria-current={active === id ? "location" : undefined}>
                                        {title}
                                    </a>
                                </li>
                            ))}
                        </ol>
                    </nav>
                    <a className="button back-link" href="#/"><Icon name="back" /> Back to Visualizer</a>
                </aside>

                <main className="guide-content">
                    <h1>How to use</h1>
                    <p className="guide-lede">Enter AArch64 assembly, select Load, then step through the recorded execution.</p>

                    <Section id="getting-started" title="Getting started">
                        <p>Load assembles the source and records execution. The workspace starts at step 0, before the first instruction. Examples below open as source; select Load to run them.</p>
                        <ReferenceTable headings={["Control", "Action"]} rows={[
                            ["Next", "Moves forward one instruction."],
                            ["Back", "Shows the previous state."],
                            ["Run / Pause", "Starts or pauses playback of recorded steps. Run stops at the next breakpoint."],
                            ["Jump to breakpoint", "Jumps straight to the next breakpoint, or to the end (or the pending input) if none is ahead."],
                            ["Speed", "Sets the delay between steps, from 0 ms to 5 s."],
                            ["Reset", "Returns to step 0."],
                            ["Step counter", "Shows the selected step and the total recorded steps. Select the step number (Edit step) to type any step and jump there; the card shows which line that step comes after, with shortcuts to the start, the end, and the breakpoint stops ahead."],
                            ["Set breakpoint", "Then click any line, or its line number, to set a breakpoint; the line is highlighted in red. Click a highlighted line the same way to clear it. Esc cancels."],
                        ]} />
                        <p>A breakpoint pauses before its line runs: the panels show the state just before it, and the editor outlines the breakpoint line with a dashed border. Select Run or Jump to breakpoint again to go past it; a breakpoint inside a loop stops on every pass. Breakpoints are kept when you edit, unless their line is removed. In predict mode they are shown but do not stop anything.</p>
                        <p>After editing, select Load again. Until then, the panels show the previous run and Next and Run are disabled. Opening the guide and returning preserves your code and selected step.</p>
                        <p>The simulator starts at <code>main</code> if defined, otherwise at the first instruction. It stops when main returns or execution reaches the end of the code.</p>
                        <CodeExample example={ex.arithmetic} onOpen={requestOpen} />
                    </Section>

                    <Section id="reading-execution" title="Reading execution">
                        <p>The editor highlights the instruction that produced the selected state. Executed instruction explains its effects. Changed register values use blue text and a left marker. Registers x0–x30 are muted until written, even if the written value is zero; memory writes use blue row highlights.</p>
                        <ReferenceTable headings={["Setting or key", "Effect"]} rows={[
                            ["Addresses", "Formats memory addresses, sp, pc, and values tracked as pointers in hex or decimal."],
                            ["Data", "Formats other numeric values in hex or decimal."],
                            ["Dark editor", "The switch in the editor's top-right corner changes the editor theme. The choice is saved in this browser."],
                            [<kbd>Tab</kbd>, "Indents the selected lines."],
                            [<><kbd>Shift</kbd> + <kbd>Tab</kbd></>, "Removes indentation."],
                            [<kbd>Esc</kbd>, "Releases keyboard focus from the editor so Tab can move to the next control."],
                        ]} />
                        <p>Syntax colors distinguish instructions, registers, numbers, labels, directives, strings, and comments. They do not indicate execution state.</p>
                    </Section>

                    <Section id="registers-flags" title="Registers & flags">
                        <ReferenceTable headings={["Register", "Meaning"]} rows={[
                            [<code>x0–x30</code>, <>64-bit general-purpose registers. <code>w0–w30</code> name their lower 32 bits; writing a w register clears the upper 32 bits of its x register.</>],
                            [<code>x0–x7</code>, "Pass integer and pointer arguments under the AArch64 calling convention. Integer and pointer results return in x0 (or w0 for 32-bit results)."],
                            [<code>x30</code>, <>The link register. <code>bl</code> writes the return address here; <code>ret</code> uses x30 by default. Preserve a return address you still need before another call overwrites it.</>],
                            [<code>sp</code>, <>The stack pointer. <code>sub sp, sp, 16</code> reserves 16 bytes; adding 16 releases them. Keep sp aligned to 16 bytes when accessing memory through sp and at function-call boundaries.</>],
                            [<code>pc</code>, "The address of the next instruction."],
                        ]} />
                        <h3>Condition flags (NZCV)</h3>
                        <p><code>cmp</code> subtracts its operands to set flags without saving the result. <code>adds</code>, <code>subs</code>, and <code>ands</code> also set flags. Conditional branches test the current flags, which may come from an earlier instruction.</p>
                        <ReferenceTable headings={["Flag", "When set"]} rows={[
                            ["N", "The result’s most significant bit is 1."],
                            ["Z", "The result is zero."],
                            ["C", "Addition produces a carry, or subtraction needs no borrow. After cmp, the first operand is at least the second as an unsigned value."],
                            ["V", "Signed arithmetic overflows the result width."],
                        ]} />
                        <p><code>beq</code> and <code>bne</code> test Z. <code>blt</code>, <code>ble</code>, <code>bgt</code>, and <code>bge</code> test signed relations; <code>blo</code>, <code>bls</code>, <code>bhi</code>, and <code>bhs</code> test unsigned relations. These relations describe the operands when the flags came from a comparison.</p>
                        <CodeExample example={ex.loop} onOpen={requestOpen} />
                    </Section>

                    <Section id="ram" title="RAM">
                        <ReferenceTable headings={["Region", "Contents"]} rows={[
                            ["Stack", <>Reserved stack space, local values, and saved registers. The simulator groups cells into colored function frames, with newer calls above older ones. <code>SP →</code> marks the stack pointer.</>],
                            ["Heap", <>Active <code>malloc</code> allocations, labeled with address and size. Freed blocks disappear.</>],
                            [<code>.data</code>, <>Writable initialized data, such as <code>.quad 3</code>.</>],
                            [<code>.bss</code>, <>Zero-initialized storage, reserved with directives such as <code>.skip</code>.</>],
                            [<code>.rodata</code>, "Read-only data, including format strings."],
                        ]} />
                        <p>Each row shows an address and up to 8 bytes. Static-data labels mark named objects; strings display as text. In stack frames, <code>[empty]</code> means no store has been recorded for that cell, not that its bytes are necessarily zero.</p>
                        <p>The byte total beside each heading counts reserved stack space, active heap allocations, or the full static-section size, including unwritten storage. Each region scrolls independently. Blue rows mark writes made by the selected instruction.</p>
                        <CodeExample example={ex.array} onOpen={requestOpen} />
                        <CodeExample example={ex.recursion} onOpen={requestOpen} />
                        <CodeExample example={ex.malloc} onOpen={requestOpen} />
                    </Section>

                    <Section id="input-output" title="Input & output">
                        <p>When execution needs input, playback pauses and an input dialog opens. Enter text and select Submit. In this simulator, Submit sends the text without adding a newline and then ends the input stream. Supply all remaining input together, such as <code>18 12</code> for two integer reads.</p>
                        <p>In the input box, <kbd>Tab</kbd> types a tab character. Press <kbd>Esc</kbd> once to make the next <kbd>Tab</kbd> move to Submit; press <kbd>Esc</kbd> again to close the dialog while leaving the program waiting. Enter input reopens it. Stdout shows output up to the selected step, preserving spaces and line breaks. It follows new output while scrolled to the bottom.</p>
                        <ReferenceTable headings={["Simulated call", "Supported behavior"]} rows={[
                            [<code>printf</code>, <>Literal text, <code>%%</code>, <code>%d</code>, <code>%u</code>, <code>%ld</code>, <code>%lu</code>, <code>%c</code>, <code>%s</code>, and <code>%p</code>, each with an optional field width such as <code>%7ld</code>. A shorter value is padded on the left with spaces and a longer one is printed in full; the returned count includes the padding. Flags, precision, and <code>*</code> widths are not supported.</>],
                            [<code>puts / putchar</code>, "Print a string followed by a newline / print one byte."],
                            [<code>scanf</code>, <>One <code>%d</code> or <code>%ld</code> conversion per call.</>],
                            [<code>fgets</code>, "Buffer address in x0, size in w1, and 0 in x2 for simulated stdin. Reads at most size − 1 bytes and adds a null terminator on success."],
                            [<code>getchar</code>, "Reads one byte, or returns EOF when input is exhausted."],
                            [<code>isspace</code>, <>Takes the character in <code>w0</code> and returns nonzero (1) for space, tab, newline, vertical tab, form feed, and carriage return, or 0 otherwise, as in the C locale. Accepts EOF or a value from 0 to 255; anything else stops with an error.</>],
                        ]} />
                        <CodeExample example={ex.greeting} onOpen={requestOpen} />
                    </Section>

                    <Section id="errors" title="Understanding errors">
                        <ReferenceTable headings={["Message", "Meaning"]} rows={[
                            ["Assembly error", "The source could not be assembled. Correct the reported line and select Load."],
                            ["Not supported", "The simulator does not support this syntax or library operation."],
                            ["Runtime error", "Execution failed. Earlier steps remain available; use Back to inspect the state before the failure."],
                            ["Instruction limit", "The run reached 10,000 instructions. Check loops and termination conditions; a long valid program can also reach this limit."],
                            ["Simulator / connection error", "The tool could not produce a result. Retry Load and check the backend if the error persists."],
                        ]} />
                        <CodeExample example={ex.nullPointer} onOpen={requestOpen} />
                    </Section>

                    <Section id="supported" title="Simulator scope">
                        <p>This is a COS 217 teaching simulator, not a complete operating system or C library. Ordinary instructions execute through Unicorn; library calls and the memory display use simulator conventions.</p>
                        <ReferenceTable headings={["Feature", "Support"]} rows={[
                            ["Sections", <><code>.text</code>, <code>.data</code>, <code>.bss</code>, and <code>.rodata</code>, alone or with <code>.section</code>.</>],
                            ["Constants", <><code>.equ</code> and <code>.set</code>, defined before use, with or without <code>#</code> on operands.</>],
                            ["Data directives", <><code>.string</code>, <code>.asciz</code>, <code>.ascii</code>, <code>.byte</code>, <code>.word</code>, <code>.quad</code>, <code>.skip</code>, and <code>.align</code>.</>],
                            ["Metadata", <><code>.global</code>, <code>.type</code>, and <code>.size</code> are accepted without affecting execution.</>],
                            ["Library calls", <><code>printf</code>, <code>puts</code>, <code>putchar</code>, <code>getchar</code>, <code>fgets</code>, <code>scanf</code>, <code>malloc</code>, <code>free</code>, <code>labs</code>, and <code>isspace</code>, called with <code>bl</code>. A source-defined function with the same name takes precedence.</>],
                            ["Limits", "10,000 instructions per run, 4 KiB of stack, 16 KiB of heap, and 256 nested calls. Input and output each have a 1 MiB limit."],
                            ["Unavailable", "Macros, other sections, file I/O, and instructions that expand into multiple machine instructions. Instructions outside the explained subset may execute without an explanation."],
                        ]} />
                    </Section>
                </main>
            </div>

            {pending && (
                <ReplaceCodeDialog
                    title={pending.title}
                    returnFocusRef={opener}
                    onCancel={() => setPending(null)}
                    onConfirm={() => {
                        const example = pending;
                        opener.current = null;
                        setPending(null);
                        onOpenExample(example);
                    }}
                />
            )}
        </div>
    );
}
