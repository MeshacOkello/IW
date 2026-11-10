import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import NumberText from "./NumberText";
import { useState, useEffect } from "react";

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
    const [loadError, setLoadError] = useState(null);
    const [stepIndex, setStepIndex] = useState(0);
    const [isRunning, setIsRunning] = useState(false);
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

    function handleRun() {
        if (history == null) return;
        if (stepIndex == history.register_states.length - 1) return;
        setIsRunning(!isRunning);
    }

    async function handleLoad() {
        setIsRunning(false);
        setLoadError(null);

        // Send assembly code to Flask server
        const response = await fetch('/simulate', {
            'method': 'POST',
            'headers': {'Content-type': 'application/json'},
            'body': JSON.stringify({assembly_code: assemblyCode})
        });

        const data = await response.json();
        if (!response.ok) {
            setHistory(null);
            setStepIndex(0);
            setLoadError(data);
            return;
        }

        setHistory(data);
        setStepIndex(0);
    }

    function handleNext() {
        setIsRunning(false)
        if (history == null) return;
        if (stepIndex < history.register_states.length - 1) {
            setStepIndex(stepIndex+1);
        }
    }

    function handleBack() {
        setIsRunning(false)
        if (stepIndex > 0) {
            setStepIndex(stepIndex-1);
        }
    }

    function handleReset() {
        setIsRunning(false);
        setStepIndex(0);
    }

    useEffect(() => {
        if (!history || !isRunning) return;
        const lastStep = history.register_states.length - 1;
        if (stepIndex >= lastStep) return;
        const timer = setTimeout(() => {
            const nextStep = stepIndex + 1;
            setStepIndex(nextStep);
            if (nextStep === lastStep) setIsRunning(false);
        }, 900);

        return () => clearTimeout(timer);
    }, [stepIndex, isRunning, history]);

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
                    <ExecutionControls onLoad={handleLoad} onNext = {handleNext} onBack={handleBack} onReset={handleReset} currentStep={stepIndex} totalSteps={history ? history.register_states.length - 1 : 0} onRun={handleRun} isRunning = {isRunning}/>

                    {loadError && (
                        <p role="alert">
                            <NumberText parts={loadError.error_parts} fallback={loadError.error} formats={formats} />
                        </p>
                    )}
                    <CodeEditor
                        assemblyCode={assemblyCode}
                        setAssemblyCode={setAssemblyCode}
                        activeLine={history?.executed_lines[stepIndex]}
                    />
                    <NextInstruction
                        assemblyCode={assemblyCode}
                        currentLine={history?.executed_lines?.[stepIndex]}
                        isLoaded={history !== null}
                        explanation={history?.explanations?.[stepIndex]}
                        explanationParts={history?.explanation_parts?.[stepIndex]}
                        formats={formats}
                    />
                </div>
                <div className="register-panel">
                <RegisterPanel
                    registerValues={registerSnapshot(history, stepIndex)}
                    previousRegisterValues={stepIndex > 0 ? registerSnapshot(history, stepIndex - 1) : null}
                    pointerRegisters={history?.pointer_states?.[stepIndex]}
                    formats={formats}
                />                </div>
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
        </div>
    );
}
