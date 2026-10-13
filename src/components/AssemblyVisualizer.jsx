import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import InputOutputPanel from "./InputOutputPanel";
import { useState, useEffect } from "react";

export default function AssemblyVisualizer() {
   const [assemblyCode, setAssemblyCode] = useState(`mov x1, #20
mov x2, #5
add x3, x1, x2
sub x4, x1, x2
mul x5, x3, x2`);

    const [history, setHistory] = useState(null);
    const [stepIndex, setStepIndex] = useState(0);
    const [isRunning, setIsRunning] = useState(false);

    function handleRun() {
        if (history == null) return;
        if (stepIndex == history.register_states.length - 1) return;
        setIsRunning(!isRunning);
    }

    async function handleLoad() {
        setIsRunning(false)

        // Send assembly code to Flask server
        const response = await fetch('/simulate', {
            'method': 'POST',
            'headers': {'Content-type': 'application/json'},
            'body': JSON.stringify({assembly_code: assemblyCode})
        });

        const data = await response.json();
        console.log(data);

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
        if (stepIndex == history.register_states.length - 1) {
            setIsRunning(false);
            return;
        }
        const timer =setTimeout(() => {setStepIndex(stepIndex+1)}, 900);

        return ()=> clearTimeout(timer);
    }, [stepIndex, isRunning, history]);

    return(
        <div className="assembly-visualizer">
            <h1>Assembly Visualizer</h1>
            
            <div className="workspace">
                <div className="code-editor">
                    <ExecutionControls onLoad={handleLoad} onNext = {handleNext} onBack={handleBack} onReset={handleReset} currentStep={stepIndex} totalSteps={history ? history.register_states.length - 1 : 0} onRun={handleRun} isRunning = {isRunning}/>
                    <NextInstruction/>
                    <CodeEditor assemblyCode = {assemblyCode} setAssemblyCode = {setAssemblyCode}/>
                    <InputOutputPanel/>
                </div>
                <div className="register-panel">
                    <RegisterPanel registerValues = {history?.register_states[stepIndex]} previousRegisterValues={stepIndex > 0 ? history.register_states[stepIndex - 1] : null}/>
                </div>
                <div className="memory-panel">
                    <MemoryPanel/>
                </div>
            </div>
        </div>
    );
}