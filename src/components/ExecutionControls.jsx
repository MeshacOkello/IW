import { RUN_DELAYS } from "../runSpeed";

export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, canPause, runDelay, onRunDelayChange, busy, sourceChanged, nextButtonRef, loadButtonRef, predictMode, onPredictModeChange, asking, hasScore}) {
    return(
        <div className="execution-controls">
            <div className="execution-buttons">
                <button ref={loadButtonRef} className="primary" onClick={onLoad}>Load</button>
                <button disabled={!busy && currentStep === 0 && !hasScore && !asking} onClick={onReset}>Reset</button>
                <button disabled={busy || currentStep === 0} onClick={onBack}>Back</button>
                <button ref={nextButtonRef} disabled={busy || sourceChanged || asking || currentStep >= totalSteps} onClick={onNext}>Next</button>
                <button className="primary" disabled={!canPause && (predictMode || busy || sourceChanged || currentStep >= totalSteps)}
                    title={predictMode && !canPause ? "Run is off in predict mode: step with Next" : undefined}
                    onClick={onRun}>{canPause ? "Pause" : "Run"}</button>
            </div>
            <div className="playback-settings">
                <label className="theme-switch predict-switch" title="Guess what each instruction changes before it runs">
                    Predict
                    <input
                        type="checkbox"
                        role="switch"
                        checked={predictMode}
                        onChange={(event) => onPredictModeChange(event.target.checked)}
                    />
                    <span className="switch-track" aria-hidden="true" />
                </label>
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
        </div>
    );
}
