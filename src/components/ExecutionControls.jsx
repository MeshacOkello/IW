import { MIN_RUN_DELAY, MAX_RUN_DELAY, runDelayFrom } from "../runSpeed";

export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, isRunning, runDelay, onRunDelayChange}) {
    return(
        <div className="execution-controls">
            <button onClick={onLoad}>Load</button>
            <button onClick={onReset}>Reset</button>
            <button onClick={onBack}>Back</button>
            <button onClick={onNext}>Next</button>
            <button onClick={onRun}>{isRunning ? "Pause" : "Run"}</button>
            <label className="run-speed" title="Delay between instructions while running">
                Speed
                <input
                    type="number"
                    min={MIN_RUN_DELAY}
                    max={MAX_RUN_DELAY}
                    step="100"
                    value={runDelay}
                    onChange={(event) => onRunDelayChange(event.target.value)}
                    onBlur={(event) => onRunDelayChange(String(runDelayFrom(event.target.value)))}
                />
                ms
            </label>
            <h5>Step {currentStep} of {totalSteps}</h5>
        </div>
    );
}
