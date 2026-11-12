import { MIN_RUN_DELAY, MAX_RUN_DELAY, runDelayFrom } from "../runSpeed";

export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, canPause, runDelay, onRunDelayChange, busy, sourceChanged, nextButtonRef}) {
    return(
        <div className="execution-controls">
            <button onClick={onLoad}>Load</button>
            <button disabled={!busy && currentStep === 0} onClick={onReset}>Reset</button>
            <button disabled={busy || currentStep === 0} onClick={onBack}>Back</button>
            <button ref={nextButtonRef} disabled={busy || sourceChanged || currentStep >= totalSteps} onClick={onNext}>Next</button>
            <button disabled={!canPause && (busy || sourceChanged || currentStep >= totalSteps)} onClick={onRun}>{canPause ? "Pause" : "Run"}</button>
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
