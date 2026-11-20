import { RUN_DELAYS } from "../runSpeed";

export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, canPause, runDelay, onRunDelayChange, busy, sourceChanged, nextButtonRef, loadButtonRef}) {
    return(
        <div className="execution-controls">
            <button ref={loadButtonRef} className="primary" onClick={onLoad}>Load</button>
            <button disabled={!busy && currentStep === 0} onClick={onReset}>Reset</button>
            <button disabled={busy || currentStep === 0} onClick={onBack}>Back</button>
            <button ref={nextButtonRef} disabled={busy || sourceChanged || currentStep >= totalSteps} onClick={onNext}>Next</button>
            <button className="primary" disabled={!canPause && (busy || sourceChanged || currentStep >= totalSteps)} onClick={onRun}>{canPause ? "Pause" : "Run"}</button>
            <label className="run-speed" title="Delay between instructions while running">
                Speed:
                <select value={runDelay} onChange={(event) => onRunDelayChange(event.target.value)}>
                    {RUN_DELAYS.map((delay) => (
                        <option key={delay} value={String(delay)}>{delay}ms</option>
                    ))}
                </select>
            </label>
            <span className="step-counter">Step {currentStep} of {totalSteps}</span>
        </div>
    );
}
