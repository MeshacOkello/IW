import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import { useState, useEffect, useRef, useCallback, useImperativeHandle } from "react";
import StdOut from "./StdOut";
import StdIn from "./StdIn";
import { extendHistory, stdoutAt, inputPrompt } from "../history";
import { DEFAULT_RUN_DELAY, runDelayFrom } from "../runSpeed";
import ErrorMessage from "./ErrorMessage";
import { fromClient, fromResponse, fromTransport } from "../errors";
import FlagsPanel from "./FlagsPanel";
import { applyTheme, initialTheme } from "../theme";
import PageNav from "./PageNav";

// Carries the normalized error rather than a bare string, so the panel can
// show the line, the source line and the suggestion alongside the message.
class SimulationFailure extends Error {
    constructor(error) {
        super(error.message);
        this.name = "SimulationFailure";
        this.error = error;
    }
}

function registerSnapshot(history, index) {
    const registers = history?.register_states[index];
    const exact = history?.exact_values?.[index]?.registers;
    return exact ? registers.map((value, register) => exact[register] ?? value) : registers;
}

const STARTER_PROGRAM = `mov x1, #20
mov x2, #5
add x3, x1, x2
sub x4, x1, x2
mul x5, x3, x2`;

// `ref` lets the How to use page put an example in the editor; `active` is
// false while that page is showing and this workspace is kept, hidden.
export default function AssemblyVisualizer({ ref, active = true }) {
    const [assemblyCode, setAssemblyCode] = useState(STARTER_PROGRAM);
    // The code as it last arrived from outside the editor: the starter
    // program or an opened example. Anything else was written here.
    const providedCode = useRef(STARTER_PROGRAM);
    const [openedExample, setOpenedExample] = useState(null);
    const loadButton = useRef(null);
    const focusLoadWhenShown = useRef(false);

    const [history, setHistory] = useState(null);
    const [run, setRun] = useState(null);
    const [busy, setBusy] = useState(false);
    const busyRef = useRef(false);
    const runId = useRef(0);
    const activeRequest = useRef(null);
    const inputDismissals = useRef(0);
    const runIntent = useRef(false);
    const [runRequested, setRunRequested] = useState(false);
    const inputButton = useRef(null);
    const nextButton = useRef(null);
    const [dismissedInput, setDismissedInput] = useState(null);
    const [inputError, setInputError] = useState(null);
    const [loadError, setLoadError] = useState(null);
    const [stepIndex, setStepIndex] = useState(0);
    const [isRunning, setIsRunning] = useState(false);
    const [runDelay, setRunDelay] = useState(String(DEFAULT_RUN_DELAY));
    const [addressFormat, setAddressFormat] = useState("hex");
    const [dataFormat, setDataFormat] = useState("dec");
    const [theme, setTheme] = useState(initialTheme);
    const formats = { address: addressFormat, data: dataFormat };

    const exactStack = history?.exact_values?.[stepIndex]?.stack;
    const stackValues = history?.stack_states[stepIndex]?.map((cell) =>
        exactStack?.[cell.address] === undefined ? cell : { ...cell, value: exactStack[cell.address] }
    );

    const heapAllocations = history?.heap_states?.[stepIndex]?.map((allocationId) => {
        const { versions, chunks } = history.heap_allocations;
        const allocation = versions[allocationId];
        return {
            address: allocation.address,
            size: allocation.size,
            contents: allocation.chunks.map((chunkId) => chunks[chunkId]).join(""),
        };
    });

    // Each step names the version of every section, as the heap does.
    const sectionContents = history?.sections?.layout?.map((section) => ({
        ...section,
        contents: history.sections.versions[history.section_states[stepIndex][section.name]] ?? "",
    }));

    const sourceChanged = run !== null && assemblyCode !== run.assembly_code;
    const lastStep = history ? history.register_states.length - 1 : 0;
    const atEnd = history !== null && stepIndex === lastStep;
    const pending = atEnd && !sourceChanged && history.status.state === 'waiting'
        ? history.status.pending : null;
    const dialogOpen = pending !== null && dismissedInput !== pending.occurrence;

    useEffect(() => applyTheme(theme), [theme]);

    useEffect(() => {
        if (!active) return;
        window.scrollTo(0, 0);
        if (focusLoadWhenShown.current) {
            focusLoadWhenShown.current = false;
            loadButton.current?.focus();
        }
    }, [active]);

    const setRunIntent = useCallback((requested) => {
        runIntent.current = requested;
        setRunRequested(requested);
    }, []);
    const canPause = isRunning || (pending !== null && runRequested);

    function handleRun() {
        if (isRunning || (pending && runIntent.current)) {
            setRunIntent(false);
            setIsRunning(false);
            return;
        }
        if (!history || busyRef.current || sourceChanged || atEnd) return;
        setRunIntent(true);
        setIsRunning(true);
    }

    function cancelRequest() {
        const request = activeRequest.current;
        activeRequest.current = null;
        request?.controller.abort();
        busyRef.current = false;
        setBusy(false);
    }

    function beginRequest(id) {
        activeRequest.current?.controller.abort();
        const request = { runId: id, controller: new AbortController() };
        activeRequest.current = request;
        busyRef.current = true;
        setBusy(true);
        return request;
    }

    function isCurrentRequest(request) {
        return activeRequest.current === request && runId.current === request.runId;
    }

    function finishRequest(request) {
        if (!isCurrentRequest(request)) return;
        activeRequest.current = null;
        busyRef.current = false;
        setBusy(false);
    }

    function changeSource(source) {
        if (busyRef.current) cancelRequest();
        setRunIntent(false);
        setAssemblyCode(source);
        setIsRunning(false);
        setOpenedExample(null);
    }

    useImperativeHandle(ref, () => ({
        // True when opening `source` would lose code written in the editor.
        hasUnsavedCode(source) {
            return assemblyCode.trim() !== ""
                && assemblyCode !== providedCode.current
                && assemblyCode !== source;
        },
        // Put a program in the editor with a clean slate, without running it.
        openProgram(source, title) {
            cancelRequest();
            runId.current++;
            setRunIntent(false);
            setIsRunning(false);
            providedCode.current = source;
            setAssemblyCode(source);
            setHistory(null);
            setRun(null);
            setStepIndex(0);
            setLoadError(null);
            setInputError(null);
            setDismissedInput(null);
            setOpenedExample(title);
            focusLoadWhenShown.current = true;
        },
    }));

    async function simulate(settings, signal) {
        let response;
        try {
            response = await fetch('/simulate', {
                method: 'POST',
                headers: { 'Content-type': 'application/json' },
                body: JSON.stringify(settings),
                signal,
            });
        } catch (error) {
            const failure = fromTransport(error);
            if (!failure) throw error;      // the request was cancelled
            throw new SimulationFailure(failure);
        }

        // An HTML error page from a proxy, or an empty body, must not surface
        // as a JSON parser error.
        const body = await response.text();
        let data;
        try {
            data = JSON.parse(body);
        } catch {
            throw new SimulationFailure(fromTransport(null, { status: response.status, body }));
        }
        // A run that failed partway still carries its recorded steps.
        if (!response.ok && !data.register_states) {
            throw new SimulationFailure(fromResponse(data, { status: response.status }));
        }
        return data;
    }

    // null means the request was cancelled, so nothing should be shown.
    function failureFrom(error) {
        return error instanceof SimulationFailure ? error.error : fromClient(error);
    }

    async function handleLoad() {
        const settings = { assembly_code: assemblyCode, execution_limit: 10000, input_events: [], id: ++runId.current };
        const request = beginRequest(settings.id);
        setRunIntent(false);
        setIsRunning(false);
        setOpenedExample(null);
        setLoadError(null);
        setInputError(null);
        setDismissedInput(null);
        setHistory(null);
        setRun(null);
        setStepIndex(0);
        try {
            const data = await simulate(settings, request.controller.signal);
            if (!isCurrentRequest(request)) return;
            setHistory(data);
            setRun(settings);
        } catch (error) {
            if (isCurrentRequest(request)) setLoadError(failureFrom(error));
        } finally {
            finishRequest(request);
        }
    }

    async function submitInput(event) {
        if (busyRef.current || !pending || !atEnd || sourceChanged || run.id !== runId.current) return;
        const request = beginRequest(run.id);
        const dismissals = inputDismissals.current;
        setInputError(null);
        setIsRunning(false);
        const settings = {
            ...run,
            input_events: [...run.input_events, { ...event, request_id: pending.request_id }],
        };
        try {
            const response = await simulate(settings, request.controller.signal);
            if (!isCurrentRequest(request)) return;
            const data = extendHistory(history, response);
            setHistory(data);
            setRun(settings);
            // The selected snapshot remains just before the input call.
            // Playback or Next will advance through every newly recorded step.
            const hasMoreSteps = stepIndex < data.register_states.length - 1;
            if (data.status.state === 'error' || (!hasMoreSteps && data.status.state !== 'waiting')) {
                setRunIntent(false);
            }
            setIsRunning(hasMoreSteps && runIntent.current && inputDismissals.current === dismissals);
        } catch (error) {
            if (isCurrentRequest(request)) setInputError(failureFrom(error));
        } finally {
            finishRequest(request);
        }
    }

    function closeInput() {
        inputDismissals.current++;
        setIsRunning(false);
        setDismissedInput(pending.occurrence);
    }

    function handleNext() {
        if (history == null || busyRef.current || sourceChanged) return;
        setRunIntent(false);
        setIsRunning(false);
        if (stepIndex < history.register_states.length - 1) {
            setStepIndex(stepIndex + 1);
        }
    }

    function handleBack() {
        if (busyRef.current) return;
        setRunIntent(false);
        setIsRunning(false);
        if (stepIndex > 0) setStepIndex(stepIndex - 1);
    }

    function handleReset() {
        cancelRequest();
        setRunIntent(false);
        setIsRunning(false);
        setInputError(null);
        setDismissedInput(pending?.occurrence ?? null);
        setStepIndex(0);
    }

    useEffect(() => {
        if (!history || !isRunning || sourceChanged || busy) return;
        const lastStep = history.register_states.length - 1;
        if (stepIndex >= lastStep) return;
        const timer = setTimeout(() => {
            const nextStep = stepIndex + 1;
            setStepIndex(nextStep);
            if (nextStep === lastStep) {
                // Waiting pauses playback without cancelling the student's Run.
                if (history.status.state !== 'waiting') setRunIntent(false);
                setIsRunning(false);
            }
        }, runDelayFrom(runDelay));

        return () => clearTimeout(timer);
    }, [stepIndex, isRunning, history, runDelay, sourceChanged, busy, setRunIntent]);

    return(
        <div className="assembly-visualizer">
            <header className="app-header">
                <div className="brand-group">
                    <h1>Assembly Visualizer</h1>
                    <PageNav current="visualizer" />
                </div>
                <div className="number-formats">
                    <label>
                        Address Format:
                        <select value={addressFormat} onChange={(event) => setAddressFormat(event.target.value)}>
                            <option value="hex">Hex</option>
                            <option value="dec">Dec</option>
                        </select>
                    </label>
                    <label>
                        Data Format:
                        <select value={dataFormat} onChange={(event) => setDataFormat(event.target.value)}>
                            <option value="hex">Hex</option>
                            <option value="dec">Dec</option>
                        </select>
                    </label>
                </div>
            </header>

            <div className="workspace">
                <section className="panel code-panel" aria-label="Code editor">
                    <div className="panel-head">
                        <h2>Code Editor</h2>
                        <label className="theme-switch">
                            Dark mode
                            <input
                                type="checkbox"
                                role="switch"
                                checked={theme === "dark"}
                                onChange={(event) => setTheme(event.target.checked ? "dark" : "light")}
                            />
                            <span className="switch-track" aria-hidden="true" />
                        </label>
                    </div>

                    <ExecutionControls onLoad={handleLoad} onNext={handleNext} onBack={handleBack} onReset={handleReset} currentStep={stepIndex} totalSteps={history ? history.register_states.length - 1 : 0} onRun={handleRun} canPause={canPause} runDelay={runDelay} onRunDelayChange={setRunDelay} busy={busy} sourceChanged={sourceChanged} nextButtonRef={nextButton} loadButtonRef={loadButton}/>

                    {loadError && <ErrorMessage error={loadError} formats={formats} />}

                    <CodeEditor
                        assemblyCode={assemblyCode}
                        setAssemblyCode={changeSource}
                        activeLine={sourceChanged ? null : history?.executed_lines[stepIndex]}
                    />

                    <NextInstruction
                        assemblyCode={run?.assembly_code ?? assemblyCode}
                        currentLine={history?.executed_lines?.[stepIndex]}
                        isLoaded={history !== null}
                        explanation={history?.explanations?.[stepIndex]}
                        explanationParts={history?.explanation_parts?.[stepIndex]}
                        formats={formats}
                    />

                    <StdOut key={run?.id ?? 'empty'} output={stdoutAt(history, stepIndex)} />

                    <div className="simulation-status" role="status">
                        {openedExample && !history && <p>Opened “{openedExample}”. Select Load to run it.</p>}
                        {sourceChanged && <p>Source edited. Load to start a new run.</p>}
                        {!sourceChanged && atEnd && history.status.state === 'completed' && (
                            <p>Execution complete.{history.status.returned && <> {history.status.returned.function} returned {history.status.returned.value}.</>}</p>
                        )}
                        {!sourceChanged && atEnd && history.status.state === 'execution_limit' && <p>Execution stopped at the instruction limit.</p>}
                        {!sourceChanged && atEnd && history.status.state === 'error' && (
                            <ErrorMessage error={fromResponse(history.status)} formats={formats} />
                        )}
                        {pending && <>
                            <span>Pending {pending.function} on line {pending.line}.</span>
                            <button ref={inputButton} disabled={busy} onClick={() => {
                                setDismissedInput(null);
                                setInputError(null);
                            }}>Enter input</button>
                        </>}
                    </div>
                </section>

                <section className="panel registers-panel" aria-label="Registers">
                    <h2>Registers</h2>
                    <RegisterPanel
                        registerValues={registerSnapshot(history, stepIndex)}
                        previousRegisterValues={stepIndex > 0 ? registerSnapshot(history, stepIndex - 1) : null}
                        pointerRegisters={history?.pointer_states?.[stepIndex]}
                        formats={formats}
                    />
                    <FlagsPanel
                        registerValues={registerSnapshot(history, stepIndex)}
                        formats={formats}
                    />
                </section>

                <section className="panel ram-panel" aria-label="RAM">
                    <h2>RAM</h2>
                    <MemoryPanel
                        stackValues={stackValues}
                        heapAllocations={heapAllocations}
                        frameValues={history?.frame_states?.[stepIndex]}
                        formats={formats}
                        stackPointer={history?.register_states?.[stepIndex]?.[31]}
                        memoryAccesses={history?.memory_accesses?.[stepIndex]}
                        sections={sectionContents}
                    />
                </section>
            </div>

            {dialogOpen && (
                <StdIn key={pending.request_id} prompt={inputPrompt(history, pending)} busy={busy}
                    error={inputError} formats={formats}
                    onSubmit={submitInput} onClose={closeInput}
                    returnFocusRef={inputButton} fallbackFocusRef={nextButton} />
            )}
        </div>
    );
}
