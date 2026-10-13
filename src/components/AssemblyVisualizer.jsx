import ExecutionControls from "./ExecutionControls";
import NextInstruction from "./NextInstruction";
import CodeEditor from "./CodeEditor";
import RegisterPanel from "./RegisterPanel";
import MemoryPanel from "./MemoryPanel";
import InputOutputPanel from "./InputOutputPanel";

export default function AssemblyVisualizer() {
    return(
        <div className="assembly-visualizer">
            <h1>Assembly Visualizer</h1>
            
            <div className="workspace">
                <div className="code-editor">
                    <ExecutionControls/>
                    <NextInstruction/>
                    <CodeEditor/>
                    <InputOutputPanel/>
                </div>
                <div className="register-panel">
                    <RegisterPanel/>
                </div>
                <div className="memory-panel">
                    <MemoryPanel/>
                </div>
            </div>
        </div>
    );
}