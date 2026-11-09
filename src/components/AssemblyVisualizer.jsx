import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import { useState, useEffect } from "react";

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
    const [memoryFormat, setMemoryFormat] = useState("hex");

    const heapAllocations = history?.heap_states?.[stepIndex]?.map((allocationId) => {
        const { versions, chunks } = history.heap_allocations;
        const allocation = versions[allocationId];
        return {
            address: allocation.address,
            size: allocation.size,
            contents: allocation.chunks.map((chunkId) => chunks[chunkId]).join(""),
        };
    });

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
            setLoadError(data.error);
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
            <h1>Assembly Visualizer</h1>
            
            <div className="workspace">
                <div className="code-panel">
                    <ExecutionControls onLoad={handleLoad} onNext = {handleNext} onBack={handleBack} onReset={handleReset} currentStep={stepIndex} totalSteps={history ? history.register_states.length - 1 : 0} onRun={handleRun} isRunning = {isRunning}/>

                    {loadError && <p role="alert">{loadError}</p>}
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
                    />
                </div>
                <div className="register-panel">
                <RegisterPanel
                    registerValues={history?.register_states[stepIndex]}
                    previousRegisterValues={
                        stepIndex > 0 ? history.register_states[stepIndex - 1] : null
                    }
                    memoryFormat={memoryFormat}
                />                </div>
                <div className="memory-panel">
                <MemoryPanel
                    stackValues={history?.stack_states[stepIndex]}
                    heapAllocations={heapAllocations}
                    frameValues={history?.frame_states?.[stepIndex]}
                    memoryFormat={memoryFormat}
                    setMemoryFormat={setMemoryFormat}
                    stackPointer={history?.register_states?.[stepIndex]?.[31]}
                    memoryAccesses={history?.memory_accesses?.[stepIndex]}
                />                </div>
            </div>
        </div>
    );
}
