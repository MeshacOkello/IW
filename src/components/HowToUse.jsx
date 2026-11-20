import { useEffect, useRef, useState } from "react";
import PageNav from "./PageNav";
import CodeExample from "./CodeExample";
import ReplaceCodeDialog from "./ReplaceCodeDialog";
import Icon from "./Icon";
import { EXAMPLES } from "../guide/examples";
import { SECTIONS } from "../guide/sections";
import "../guide/guide.css";

const SYNTAX_COLORS = [
    { kind: "directive", sample: ".section", meaning: "directives" },
    { kind: "label", sample: "main:", meaning: "labels" },
    { kind: "mnemonic", sample: "add", meaning: "instructions" },
    { kind: "register", sample: "x3", meaning: "registers" },
    { kind: "immediate", sample: "25", meaning: "numbers" },
    { kind: "string", sample: '"%ld"', meaning: "strings" },
    { kind: "comment", sample: "// note", meaning: "comments" },
];

function Section({ id, number, title, intro, children }) {
    return (
        <section className="guide-section" id={id} aria-labelledby={`${id}-heading`}>
            <h2 id={`${id}-heading`} tabIndex={-1}>
                {number && <span className="section-number">{number}.</span>} {title}
            </h2>
            {intro && <p className="section-intro">{intro}</p>}
            {children}
        </section>
    );
}

function Term({ name, children }) {
    return (
        <div className="term">
            <dt>{name}</dt>
            <dd>{children}</dd>
        </div>
    );
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
            <header className="app-header guide-header">
                <div className="brand-group">
                    <a className="brand" href="#/">Assembly Visualizer</a>
                    <PageNav current="guide" />
                </div>
            </header>

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
                    <p className="guide-lede">Learn the controls, then try a small program. Every example opens in the Visualizer, ready to run.</p>

                    <Section id="getting-started" number={1} title="Load your first program"
                        intro="Write assembly in the Code Editor, select Load, then move through the steps.">
                        <ol className="stepper" aria-label="The three steps">
                            <li><span aria-hidden="true">1</span> Write code</li>
                            <li><span aria-hidden="true">2</span> Load</li>
                            <li><span aria-hidden="true">3</span> Step or Run</li>
                        </ol>

                        <div className="split">
                            <div>
                                <p><strong>Load</strong> assembles your program and records every step it takes. The panels then show the state before the first instruction.</p>
                                <ul className="control-list">
                                    <li><strong>Next</strong> executes one instruction.</li>
                                    <li><strong>Back</strong> returns to the state before the last instruction.</li>
                                    <li><strong>Run</strong> plays the steps one after another. <strong>Pause</strong> stops it.</li>
                                    <li><strong>Speed</strong> sets the wait between steps while running, from 0 ms to 5 s.</li>
                                    <li><strong>Reset</strong> goes back to step 0, before the first instruction.</li>
                                    <li><strong>Step 3 of 12</strong> counts the instructions run so far, out of all the steps recorded.</li>
                                </ul>
                                <p className="callout">Edited your code? The panels keep showing the old run, and Next and Run stay off, until you select <strong>Load</strong> again.</p>
                                <p>A program starts at <code>main</code> when it has one, and otherwise at its first instruction. It ends when <code>main</code> returns, or after its last instruction.</p>
                            </div>
                            <CodeExample example={ex.arithmetic} onOpen={requestOpen} />
                        </div>
                    </Section>

                    <Section id="reading-execution" number={2} title="Read what changed"
                        intro="Each step connects one instruction to its effects.">
                        <div className="change-demo" aria-hidden="true">
                            <code className="change-chip">
                                <span className="tok-mnemonic">add</span> <span className="tok-register">x3</span>, <span className="tok-register">x1</span>, <span className="tok-register">x2</span>
                            </code>
                            <span className="change-arrow">→</span>
                            <code className="change-chip changed"><span className="tok-register">x3</span> <span className="change-divider">|</span> <span className="tok-immediate">25</span></code>
                        </div>
                        <dl className="terms two-column">
                            <Term name="Executed instruction">
                                The line just executed is highlighted in the editor, with its line number in bold. The Executed Instruction panel repeats it and explains what it did, using the actual values.
                            </Term>
                            <Term name="Changed values">
                                Registers the last step changed are highlighted in blue. So are memory rows it wrote to, in Stack, Heap, .data and .bss.
                            </Term>
                            <Term name="Address and data formats">
                                <strong>Address Format</strong> shows addresses (sp, pc, pointers and memory addresses) in hex or decimal. <strong>Data Format</strong> does the same for every other value.
                            </Term>
                            <Term name="Editor">
                                <kbd>Tab</kbd> indents and <kbd>Shift</kbd>+<kbd>Tab</kbd> outdents. Press <kbd>Esc</kbd> to leave the editor with the keyboard. The <strong>Dark mode</strong> switch sits in the Code Editor heading, and your choice is remembered.
                            </Term>
                        </dl>
                        <h3 className="subheading">Syntax colors</h3>
                        <ul className="syntax-legend">
                            {SYNTAX_COLORS.map(({ kind, sample, meaning }) => (
                                <li key={kind}><code className={`tok-${kind}`}>{sample}</code> {meaning}</li>
                            ))}
                        </ul>
                    </Section>

                    <Section id="registers-flags" number={3} title="Registers & flags"
                        intro="Registers are the processor's own variables. Each holds 64 bits.">
                        <dl className="terms two-column">
                            <Term name="x0 to x30">
                                General-purpose registers. <code>w0</code> to <code>w30</code> name their lower 32 bits. A function gets its arguments in x0 to x7 and returns its result in x0.
                            </Term>
                            <Term name="x30">
                                The return address. <code>bl</code> puts it there, and <code>ret</code> jumps back to it. Save x30 on the stack before calling another function.
                            </Term>
                            <Term name="sp">
                                The stack pointer: the lowest address the stack is using. <code>sub sp, sp, 16</code> reserves space, and adding it back releases the space. Keep sp a multiple of 16.
                            </Term>
                            <Term name="pc">
                                The program counter: the address of the next instruction to run.
                            </Term>
                        </dl>

                        <h3 className="subheading">NZCV flags</h3>
                        <p>Instructions such as <code>cmp</code>, <code>adds</code> and <code>subs</code> set four flags, shown under the registers. Conditional branches read them.</p>
                        <dl className="flag-terms">
                            <Term name="N">Negative: the result was negative.</Term>
                            <Term name="Z">Zero: the result was 0, so a compare found the values equal.</Term>
                            <Term name="C">Carry: for a compare, the first value was at least the second, read as unsigned.</Term>
                            <Term name="V">Overflow: the signed result did not fit.</Term>
                        </dl>
                        <p><code>beq</code> and <code>bne</code> test Z. <code>blt</code>, <code>ble</code>, <code>bgt</code> and <code>bge</code> compare signed values. <code>blo</code> and <code>bhi</code> compare unsigned ones.</p>
                        <CodeExample example={ex.loop} onOpen={requestOpen} />
                    </Section>

                    <Section id="ram" number={4} title="RAM"
                        intro="Each region of memory has its own box, and each box scrolls on its own.">
                        <dl className="terms two-column">
                            <Term name="Stack">Local variables and saved registers. Each call gets a coloured frame named after its function: main sits at the bottom, newer calls stack on top, and <code>SP →</code> marks the stack pointer.</Term>
                            <Term name="Heap">Blocks from <code>malloc</code>, each labelled with its address and size. A block disappears when it is freed.</Term>
                            <Term name=".data">Variables with starting values, such as <code>.quad 3</code>. Your program can change them.</Term>
                            <Term name=".bss">Variables that start as zero, reserved with <code>.skip</code>.</Term>
                            <Term name=".rodata">Read-only constants, such as format strings. Strings are shown as text.</Term>
                        </dl>
                        <ul className="plain-list">
                            <li>Each row shows an <strong>Address</strong> and up to 8 bytes of <strong>Data</strong> stored there. In .data, .bss and .rodata, labels mark where each named variable starts.</li>
                            <li><strong>[empty]</strong> means the space is reserved but nothing has been stored there yet.</li>
                            <li>Rows the last step wrote to are <span className="written-sample">highlighted</span>.</li>
                            <li>A long list scrolls inside its box. A wide value scrolls sideways.</li>
                        </ul>
                        <CodeExample example={ex.array} onOpen={requestOpen} />
                        <CodeExample example={ex.recursion} onOpen={requestOpen} />
                        <CodeExample example={ex.malloc} onOpen={requestOpen} />
                    </Section>

                    <Section id="input-output" number={5} title="Input & output"
                        intro="Programs read input with scanf, fgets or getchar, and write output with printf, puts or putchar.">
                        <dl className="terms two-column">
                            <Term name="The input box">
                                When a program needs input, Run pauses and an input box opens, headed by the program's last prompt. Type your input and select <strong>Submit</strong>.
                                Submit also ends the input, so later reads find nothing left. If a program asks twice, answer both in one box, such as <code>18 12</code>.
                            </Term>
                            <Term name="Closing it">
                                <kbd>Esc</kbd> closes the box without answering. The program waits, and <strong>Enter input</strong> under the editor opens the box again.
                            </Term>
                            <Term name="Stdout">
                                Shows what the program printed up to the selected step, so Back takes later output away again. Spaces and line breaks are kept, and the panel scrolls, following the newest line while you are at the bottom.
                            </Term>
                            <Term name="Conventions">
                                For <code>fgets</code>, put 0 in x2 to read from stdin. <code>scanf</code> reads one <code>%d</code> or <code>%ld</code> per call.
                            </Term>
                        </dl>
                        <CodeExample example={ex.greeting} onOpen={requestOpen} />
                    </Section>

                    <Section id="errors" number={6} title="Understanding errors"
                        intro="Every error names its kind, and its line when it has one.">
                        <dl className="terms two-column">
                            <Term name="Assembly error">The program could not be assembled, so nothing ran. The message above the editor shows the line, what is wrong and often a fix. Correct it and select Load.</Term>
                            <Term name="Not supported">Valid assembly that the simulator does not handle, such as a <code>.macro</code> or a <code>%f</code> in printf.</Term>
                            <Term name="Runtime error">The program ran, then failed, for example by reading memory it does not own or freeing a block twice. Every step before the failure stays recorded.</Term>
                            <Term name="Instruction limit">A run stops after 10,000 instructions, usually because of a loop that never ends. Programs also stop at 256 nested calls.</Term>
                        </dl>
                        <p className="callout">To find what caused a runtime error, select <strong>Back</strong> from the end and watch the values that led up to it.</p>
                        <CodeExample example={ex.nullPointer} onOpen={requestOpen} />
                        <p className="note">Messages labelled <strong>Simulator error</strong> or <strong>Cannot reach the simulator</strong> are a problem with the tool, not your program. Load again, and if it keeps happening, report it.</p>
                    </Section>

                    <Section id="supported" title="What's supported"
                        intro="The Visualizer covers the AArch64 subset used in COS 217.">
                        <dl className="terms support-terms">
                            <Term name="Sections">
                                <code>.text</code>, <code>.data</code>, <code>.bss</code> and <code>.rodata</code>, written alone or with <code>.section</code>.
                            </Term>
                            <Term name="Directives">
                                Constants with <code>.equ</code> or <code>.set</code>, used with or without <code>#</code>, defined above their first use. Data with <code>.string</code>, <code>.asciz</code>, <code>.ascii</code>, <code>.byte</code>, <code>.word</code>, <code>.quad</code>, <code>.skip</code> and <code>.align</code>. <code>.global</code>, <code>.type</code> and <code>.size</code> are accepted and change nothing.
                            </Term>
                            <Term name="Library calls">
                                With <code>bl</code>: <code>printf</code> (%d, %u, %ld, %lu, %c, %s, %p), <code>puts</code>, <code>putchar</code>, <code>getchar</code>, <code>fgets</code>, <code>scanf</code>, <code>malloc</code>, <code>free</code> and <code>labs</code>. A function you write with the same name runs instead.
                            </Term>
                            <Term name="Limits">
                                10,000 instructions per run, a 4 KiB stack, a 16 KiB heap and 256 nested calls.
                            </Term>
                            <Term name="Not available">
                                Macros, other sections, files other than stdin and stdout, and instructions that expand to more than one machine instruction. Instructions outside the COS 217 set may run without an explanation.
                            </Term>
                        </dl>
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
