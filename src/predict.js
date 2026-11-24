// Predict mode: which fields a student is asked about for the instruction
// between two recorded snapshots, and how their answers are scored.
//
// Nothing here touches React. The snapshots are the trace the backend
// records, read at step `step` (before the instruction) and `step + 1`
// (after it).

export const SP = 31;
export const PC = 32;
export const NZCV = 33;

const FLAGS = ["N", "Z", "C", "V"];
const LIBRARY_FUNCTIONS = new Set([
    "malloc", "free", "printf", "puts", "putchar", "getchar", "fgets", "scanf", "labs", "isspace",
]);
const CONDITIONS = "eq|ne|lt|le|gt|ge|lo|ls|hi|hs|cc|cs|mi|pl|vs|vc|al|nv";
const CONDITIONAL_BRANCH = new RegExp(`^b\\.?(?:${CONDITIONS})$`);
const FLAG_SETTERS = new Set([
    "cmp", "cmn", "tst", "adds", "subs", "ands", "negs", "bics", "adcs", "sbcs", "ccmp", "ccmn",
]);
// Instructions whose first operand is read, not written.
const NO_DESTINATION = new Set(["cmp", "cmn", "tst", "ccmp", "ccmn", "nop", "b", "br", "ret"]);
const STORE_BYTES = { strb: 1, sturb: 1, strh: 2, sturh: 2 };
const STORES = new Set(["str", "strb", "strh", "stur", "sturb", "sturh", "stp", "stnp"]);
const PAIR_LOADS = new Set(["ldp", "ldnp", "ldpsw"]);

const UINT64_LIMIT = 1n << 64n;
const INT64_MIN = -(1n << 63n);

// ---------------------------------------------------------------------------
// Reading source

export function stripSource(line) {
    let text = (line ?? "").split("//")[0].trim();
    for (;;) {
        const label = /^[A-Za-z_.$][\w.$]*:\s*/.exec(text);
        if (!label) return text;
        text = text.slice(label[0].length).trim();
    }
}

// Split on commas outside brackets and character quotes.
export function splitOperands(text) {
    const parts = [];
    let depth = 0, quote = false, current = "";
    for (const char of text) {
        if (char === "'") quote = !quote;
        else if (!quote && char === "[") depth++;
        else if (!quote && char === "]") depth--;
        if (char === "," && depth === 0 && !quote) {
            parts.push(current.trim());
            current = "";
        } else {
            current += char;
        }
    }
    if (current.trim()) parts.push(current.trim());
    return parts;
}

// { index, bits, name } for a register operand; index is null for xzr/wzr.
export function parseRegister(text) {
    const name = (text ?? "").trim().toLowerCase();
    if (name === "sp") return { index: SP, bits: 64, name };
    if (name === "wsp") return { index: SP, bits: 32, name };
    if (name === "xzr") return { index: null, bits: 64, name };
    if (name === "wzr") return { index: null, bits: 32, name };
    if (name === "fp") return { index: 29, bits: 64, name };
    if (name === "lr") return { index: 30, bits: 64, name };
    const match = /^([xw])(\d+)$/.exec(name);
    if (match && Number(match[2]) <= 30) {
        return { index: Number(match[2]), bits: match[1] === "x" ? 64 : 32, name };
    }
    return null;
}

// What an instruction can change, decided from its text alone, so the fields
// a student sees never depend on what actually happened.
export function decodeInstruction(line) {
    const text = stripSource(line);
    const [word = "", rest = ""] = text.split(/\s+(.*)/s);
    const mnemonic = word.toLowerCase();
    const operands = rest ? splitOperands(rest) : [];
    const info = {
        text, mnemonic, operands,
        destinations: [],
        setsFlags: FLAG_SETTERS.has(mnemonic),
        branch: null,
        libraryCall: null,
        store: null,
    };

    const addDestination = (register) => {
        if (register && register.index !== null && !info.destinations.some((d) => d.index === register.index)) {
            info.destinations.push(register);
        }
    };

    if (["b", "bl", "br", "blr", "ret"].includes(mnemonic)) info.branch = "unconditional";
    else if (CONDITIONAL_BRANCH.test(mnemonic) || ["cbz", "cbnz", "tbz", "tbnz"].includes(mnemonic)) {
        info.branch = "conditional";
    }
    if (mnemonic === "bl" || mnemonic === "blr") {
        addDestination({ index: 30, bits: 64, name: "x30" });
        if (mnemonic === "bl" && LIBRARY_FUNCTIONS.has(operands[0])) info.libraryCall = operands[0];
        return info;
    }
    if (info.branch) return info;

    const memoryAt = operands.findIndex((operand) => operand.startsWith("["));
    if (memoryAt >= 0) {
        const memory = operands[memoryAt];
        const base = parseRegister(memory.slice(1).split(/[,\]]/)[0]);
        const preIndex = /\]\s*!$/.test(memory);
        const postIndex = !preIndex && operands.length > memoryAt + 1;
        const sources = operands.slice(0, memoryAt).map(parseRegister);
        if (STORES.has(mnemonic)) {
            info.store = {
                sources,
                bytes: STORE_BYTES[mnemonic] ?? (sources[0]?.bits === 32 ? 4 : 8),
            };
        } else if (PAIR_LOADS.has(mnemonic)) {
            sources.slice(0, 2).forEach(addDestination);
        } else {
            addDestination(sources[0]);
        }
        if ((preIndex || postIndex) && base) addDestination({ ...base, bits: 64 });
        return info;
    }

    if (!NO_DESTINATION.has(mnemonic) && !STORES.has(mnemonic)) {
        addDestination(parseRegister(operands[0]));
    }
    return info;
}

// ---------------------------------------------------------------------------
// Reading snapshots

export function registersAt(history, step) {
    const registers = history.register_states[step];
    const exact = history.exact_values?.[step]?.registers;
    return registers.map((value, index) => BigInt(exact?.[index] ?? value));
}

function stackByte(history, step, address) {
    const exact = history.exact_values?.[step]?.stack;
    for (const cell of history.stack_states?.[step] ?? []) {
        if (address < cell.address || address >= cell.address + cell.size) continue;
        if (cell.value == null) return null;
        const value = BigInt(exact?.[cell.address] ?? cell.value);
        return Number((value >> BigInt(8 * (address - cell.address))) & 0xffn);
    }
    return undefined;
}

function hexByte(contents, offset) {
    const pair = contents.slice(offset * 2, offset * 2 + 2);
    return pair.length === 2 && pair !== "??" ? parseInt(pair, 16) : null;
}

function heapAllocations(history, step) {
    const { versions = [], chunks = [] } = history.heap_allocations ?? {};
    return (history.heap_states?.[step] ?? []).map((id) => ({
        address: versions[id].address,
        size: versions[id].size,
        contents: versions[id].chunks.map((chunk) => chunks[chunk]).join(""),
    }));
}

function sectionsAt(history, step) {
    return (history.sections?.layout ?? [])
        .filter((section) => section.size > 0 && section.address != null)
        .map((section) => ({
            ...section,
            contents: history.sections.versions[history.section_states[step][section.name]] ?? "",
        }));
}

function contains(region, address) {
    return address >= region.address && address < region.address + region.size;
}

// Where an address lives in the RAM panel at `step`: "stack", "heap", a
// section name, or "memory" when no displayed region holds it.
export function regionOf(history, step, address) {
    const inFrame = (history.frame_states?.[step] ?? [])
        .some((frame) => address >= frame.stack_start && address < frame.stack_end);
    if (inFrame || stackByte(history, step, address) !== undefined) return "stack";
    if (heapAllocations(history, step).some((allocation) => contains(allocation, address))) return "heap";
    return sectionsAt(history, step).find((section) => contains(section, address))?.name ?? "memory";
}

// The little-endian value of `size` bytes at `address`, or null if any byte
// is not recorded in the snapshot.
export function readMemory(history, step, address, size) {
    const allocations = heapAllocations(history, step);
    const sections = sectionsAt(history, step);
    let value = 0n;
    for (let offset = size - 1; offset >= 0; offset--) {
        const at = address + offset;
        let byte = stackByte(history, step, at);
        if (byte === undefined) {
            const region = allocations.find((allocation) => contains(allocation, at))
                ?? sections.find((section) => contains(section, at));
            byte = region ? hexByte(region.contents, at - region.address) : null;
        }
        if (byte == null) return null;
        value = (value << 8n) | BigInt(byte);
    }
    return value;
}

function flagBit(nzcv, flag) {
    return Number((nzcv >> BigInt(31 - FLAGS.indexOf(flag))) & 1n);
}

// ---------------------------------------------------------------------------
// The question for one instruction

// Fields for the instruction that runs between `step` and `step + 1`. Each
// field carries its own answer (`expected`), so the UI must not render it
// until the answer is checked or revealed.
export function predictionFields(history, step, sourceLine) {
    const info = decodeInstruction(sourceLine);
    const before = registersAt(history, step);
    const after = registersAt(history, step + 1);
    const fields = [];

    // Registers the instruction type writes, plus any that changed anyway (an
    // instruction this decoder does not know). A library call's x0 is its
    // return value, which the student cannot work out, so it is left out.
    const registers = new Map(info.destinations.map((register) => [register.index, register]));
    if (!info.libraryCall) {
        for (let index = 0; index <= SP; index++) {
            if (before[index] !== after[index] && !registers.has(index)) {
                registers.set(index, { index, bits: 64, name: index === SP ? "sp" : `x${index}` });
            }
        }
    }
    for (const register of [...registers.values()].sort((a, b) => a.index - b.index)) {
        fields.push({
            id: `reg:${register.index}`,
            kind: "register",
            register: register.index,
            bits: register.index === SP ? 64 : register.bits,
            label: register.index === SP ? "sp" : register.name,
            initial: before[register.index],
            expected: after[register.index],
        });
    }

    if (info.branch) {
        const taken = info.branch === "unconditional" || after[PC] !== before[PC] + 4n;
        fields.push({ id: "branch", kind: "branch", label: "branch", expected: taken ? "taken" : "not-taken" });
    }

    // Every flag is asked about whenever the instruction sets flags, changed
    // or not.
    if (info.setsFlags || (!info.libraryCall && before[NZCV] !== after[NZCV])) {
        for (const flag of FLAGS) {
            fields.push({
                id: `flag:${flag}`,
                kind: "flag",
                flag,
                label: `${flag} flag`,
                initial: BigInt(flagBit(before[NZCV], flag)),
                expected: BigInt(flagBit(after[NZCV], flag)),
            });
        }
    }

    if (info.store) {
        const writes = (history.memory_accesses?.[step + 1] ?? []).filter((access) => access.kind === "write");
        if (writes.length) {
            const start = Math.min(...writes.map((write) => write.address));
            const count = info.mnemonic === "stp" || info.mnemonic === "stnp" ? 2 : 1;
            for (let slot = 0; slot < count; slot++) {
                const address = start + slot * info.store.bytes;
                const bits = info.store.bytes * 8;
                const source = info.store.sources[slot];
                const fromRegister = source?.index == null ? 0n : before[source.index];
                const stored = readMemory(history, step + 1, address, info.store.bytes) ?? fromRegister;
                const region = regionOf(history, step + 1, address);
                const name = count > 1 ? ` ${slot + 1}` : "";
                fields.push({
                    id: `mem:${slot}:address`, kind: "address", slot, region, bytes: info.store.bytes,
                    label: `store${name} address`, expected: BigInt(address),
                });
                fields.push({
                    id: `mem:${slot}:value`, kind: "value", slot, region, bytes: info.store.bytes, bits,
                    label: `stored value${name}`, expected: BigInt.asUintN(bits, stored),
                });
            }
        }
    }

    return { info, fields };
}

// ---------------------------------------------------------------------------
// Answers

// "0x…" is hex, anything else decimal; either may be negative. Values outside
// what 64 bits can hold, signed or unsigned, are refused rather than wrapped.
export function parseNumberInput(text) {
    const match = /^([+-]?)\s*(0x[0-9a-f]+|\d+)$/i.exec(String(text ?? "").trim());
    if (!match) return null;
    const magnitude = BigInt(match[2].toLowerCase());
    const value = match[1] === "-" ? -magnitude : magnitude;
    return value < INT64_MIN || value >= UINT64_LIMIT ? null : value;
}

// A w register holds 32 bits with the top half cleared, so -1 is a right
// answer for `mov w0, -1` even though x0 reads 0xFFFFFFFF.
function registerMatches(given, expected, bits) {
    if (BigInt.asUintN(64, given) === expected) return true;
    return bits === 32 && given >= -(1n << 31n) && given < (1n << 32n)
        && BigInt.asUintN(32, given) === expected;
}

function checkField(field, answer) {
    if (field.kind === "branch") {
        if (answer == null) return { status: "missing", correct: false };
        return { status: answer === field.expected ? "correct" : "wrong", correct: answer === field.expected, given: answer };
    }
    // Registers and flags start out holding their current value.
    const text = answer ?? (field.initial !== undefined ? field.initial.toString() : "");
    if (String(text).trim() === "") return { status: "missing", correct: false };
    const given = parseNumberInput(text);
    if (given === null) return { status: "invalid", correct: false, given: String(text) };
    let correct;
    if (field.kind === "register") correct = registerMatches(given, field.expected, field.bits);
    else if (field.kind === "flag") correct = given === field.expected;
    else if (field.kind === "value") correct = BigInt.asUintN(field.bits, given) === field.expected;
    else correct = BigInt.asUintN(64, given) === field.expected;
    return { status: correct ? "correct" : "wrong", correct, given };
}

export function checkPredictions(fields, answers = {}) {
    const results = {};
    let correct = 0;
    for (const field of fields) {
        results[field.id] = checkField(field, answers[field.id]);
        if (results[field.id].correct) correct++;
    }
    return { results, correct, total: fields.length };
}

// ---------------------------------------------------------------------------
// Session score

const MISSED_LIMIT = 8;

export function emptyScore() {
    return { correct: 0, total: 0, scoredSteps: [], missed: [] };
}

// Count a check once per step: going Back and predicting the same
// instruction again is practice, not a second score.
export function recordCheck(score, { step, line, instruction, fields, check }) {
    if (score.scoredSteps.includes(step)) return { score, counted: false };
    const wrong = fields
        .filter((field) => !check.results[field.id].correct)
        .map((field) => ({ field, result: check.results[field.id] }));
    const missed = wrong.length
        ? [...score.missed, { step, line, instruction, wrong }].slice(-MISSED_LIMIT)
        : score.missed;
    return {
        counted: true,
        score: {
            correct: score.correct + check.correct,
            total: score.total + check.total,
            scoredSteps: [...score.scoredSteps, step],
            missed,
        },
    };
}

// ---------------------------------------------------------------------------
// Display

// The field with this id in a predict view (see PredictFields.jsx), if any.
export function fieldFor(predict, id) {
    return predict?.fields.find((field) => field.id === id) ?? null;
}

// An unsigned value as the panels show it; in decimal, a value with its top
// bit set also shows what it means as a signed number.
export function formatValue(value, bits, format) {
    const unsigned = BigInt.asUintN(bits, BigInt(value));
    if (format !== "dec") return "0x" + unsigned.toString(16).toUpperCase();
    const signed = BigInt.asIntN(bits, unsigned);
    return signed < 0n ? `${unsigned} (${signed})` : unsigned.toString();
}

// `isAddress` says whether the Registers table shows this register as an
// address, so the answer reads the same way as the table.
export function describeAnswer(field, value, formats, isAddress = false) {
    if (field.kind === "branch") return value === "taken" ? "taken" : "not taken";
    if (field.kind === "flag") return String(value);
    if (field.kind === "address") return formatValue(value, 64, formats.address);
    if (field.kind === "value") return formatValue(value, field.bits, formats.data);
    return formatValue(value, 64, isAddress || field.register === SP ? formats.address : formats.data);
}
