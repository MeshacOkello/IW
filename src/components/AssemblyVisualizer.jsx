import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import Section from "./Section";
import NumberText from "./NumberText";
import { useState, useEffect, useRef, useCallback } from "react";
import StdOut from "./StdOut";
import StdIn from "./StdIn";
import { extendHistory, stdoutAt, inputPrompt } from "../history";
import { DEFAULT_RUN_DELAY, runDelayFrom } from "../runSpeed";

function registerSnapshot(history, index) {
    const registers = history?.register_states[index];
    const exact = history?.exact_values?.[index]?.registers;
    return exact ? registers.map((value, register) => exact[register] ?? value) : registers;
}

export default function AssemblyVisualizer() {
   const [assemblyCode, setAssemblyCode] = useState(`mov x1, #20
mov x2, #5
add x3, x1, x2
sub x4, x1, x2
mul x5, x3, x2`);

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
    }

    async function simulate(settings, signal) {
        const response = await fetch('/simulate', {
            method: 'POST',
            headers: { 'Content-type': 'application/json' },
            body: JSON.stringify(settings),
            signal,
        });
        const data = await response.json();
        if (!response.ok && !data.register_states) {
            throw new Error(data.error || 'The simulation request failed.');
        }
        return data;
    }

    async function handleLoad() {
        const settings = { assembly_code: assemblyCode, execution_limit: 10000, input_events: [], id: ++runId.current };
        const request = beginRequest(settings.id);
        setRunIntent(false);
        setIsRunning(false);
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
            if (isCurrentRequest(request)) setLoadError({ error: error.message });
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
            if (isCurrentRequest(request)) setInputError(error.message);
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
            <header className="visualizer-header">
                <h1>Assembly Visualizer</h1>
                <div className="number-formats">
                    <label>
                        Address Format
                        <select value={addressFormat} onChange={(event) => setAddressFormat(event.target.value)}>
                            <option value="hex">Hex</option>
                            <option value="dec">Dec</option>
                        </select>
                    </label>
                    <label>
                        Data Format
                        <select value={dataFormat} onChange={(event) => setDataFormat(event.target.value)}>
                            <option value="hex">Hex</option>
                            <option value="dec">Dec</option>
                        </select>
                    </label>
                </div>
            </header>
            
            <div className="workspace">
                <div className="code-panel">
                    <ExecutionControls onLoad={handleLoad} onNext = {handleNext} onBack={handleBack} onReset={handleReset} currentStep={stepIndex} totalSteps={history ? history.register_states.length - 1 : 0} onRun={handleRun} canPause={canPause} runDelay={runDelay} onRunDelayChange={setRunDelay} busy={busy} sourceChanged={sourceChanged} nextButtonRef={nextButton}/>

                    {loadError && (
                        <p role="alert">
                            <NumberText parts={loadError.error_parts} fallback={loadError.error} formats={formats} />
                        </p>
                    )}
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
                        {sourceChanged && <p>Source edited. Load to start a new run.</p>}
                        {!sourceChanged && atEnd && history.status.state === 'completed' && <p>Execution complete.</p>}
                        {!sourceChanged && atEnd && history.status.state === 'execution_limit' && <p>Execution stopped at the instruction limit.</p>}
                        {!sourceChanged && atEnd && history.status.state === 'error' && (
                            <p role="alert"><NumberText parts={history.status.error_parts} fallback={history.status.error} formats={formats} /></p>
                        )}
                        {pending && <>
                            <span>Pending {pending.function} on line {pending.line}.</span>
                            <button ref={inputButton} disabled={busy} onClick={() => {
                                setDismissedInput(null);
                                setInputError(null);
                            }}>Enter input</button>
                        </>}
                    </div>
                </div>
                <div className="register-column">
                <div className="register-panel">
                <RegisterPanel
                    registerValues={registerSnapshot(history, stepIndex)}
                    previousRegisterValues={stepIndex > 0 ? registerSnapshot(history, stepIndex - 1) : null}
                    pointerRegisters={history?.pointer_states?.[stepIndex]}
                    formats={formats}
                />                </div>
                <div className="rodata-panel">
                <Section
                    name=".rodata"
                    section={sectionContents?.find((section) => section.name === ".rodata")}
                    formats={formats}
                    memoryAccesses={history?.memory_accesses?.[stepIndex]}
                />                </div>
                </div>
                <div className="memory-panel">
                <MemoryPanel
                    stackValues={stackValues}
                    heapAllocations={heapAllocations}
                    frameValues={history?.frame_states?.[stepIndex]}
                    formats={formats}
                    stackPointer={history?.register_states?.[stepIndex]?.[31]}
                    memoryAccesses={history?.memory_accesses?.[stepIndex]}
                    sections={sectionContents}
                />                </div>
            </div>
            {dialogOpen && (
                <StdIn key={pending.request_id} prompt={inputPrompt(history, pending)} busy={busy} error={inputError}
                    onSubmit={submitInput} onClose={closeInput}
                    returnFocusRef={inputButton} fallbackFocusRef={nextButton} />
            )}
        </div>
    );
}
