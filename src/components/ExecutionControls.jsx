export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, isRunning}) {
    return(
        <div className="execution-controls">
            <button onClick={onLoad}>Load</button>
            <button onClick={onReset}>Reset</button>
            <button onClick={onBack}>Back</button>
            <button onClick={onNext}>Next</button>
            <button onClick={onRun}>{isRunning ? "Pause" : "Run"}</button>
            <h5>Step {currentStep} of {totalSteps}</h5>
        </div>
    );
}