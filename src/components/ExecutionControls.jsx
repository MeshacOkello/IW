import { RUN_DELAYS } from "../runSpeed";
import StepJump from "./StepJump";

// Every action button on one row.
export default function ExecutionControls({onLoad, onNext, onBack, onReset, onRun, currentStep, totalSteps, canPause, busy, sourceChanged, nextButtonRef, loadButtonRef, predictMode, asking, hasScore, onJumpToBreakpoint, hasBreakpoints, pickingBreakpoint, breakpointCount, onToggleBreakpointPicking, breakpointButtonRef}) {
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
                <button disabled={predictMode || busy || sourceChanged || currentStep >= totalSteps}
                    title={predictMode ? "Breakpoints don't stop anything in predict mode"
                        : hasBreakpoints ? "Jump to the next breakpoint, or the end if none is ahead"
                        : "No breakpoints set: jumps to the end"}
                    onClick={onJumpToBreakpoint}>Jump to breakpoint</button>
                <button
                    ref={breakpointButtonRef}
                    type="button"
                    className={`breakpoint-button${pickingBreakpoint ? " picking" : ""}`}
                    aria-pressed={pickingBreakpoint}
                    title={pickingBreakpoint ? "Stop choosing a line (Esc)" : "Choose a line to stop on"}
                    onClick={onToggleBreakpointPicking}
                >
                    {pickingBreakpoint ? "Cancel" : "Set breakpoint"}
                    {!pickingBreakpoint && breakpointCount > 0 && (
                        <span className="breakpoint-count" aria-label={`, ${breakpointCount} set`}>{breakpointCount}</span>
                    )}
                </button>
            </div>
        </div>
    );
}

// Predict, Speed and the step counter, which sit beside the panel's title.
export function PlaybackSettings({ predictMode, onPredictModeChange, runDelay, onRunDelayChange, currentStep, totalSteps, canJump, onJump, summarizeStep, breakpointStops }) {
    return (
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
            <label className="run-speed" title="Playback speed: the delay between instructions while running">
                Speed
                <select value={runDelay} onChange={(event) => onRunDelayChange(event.target.value)}>
                    {RUN_DELAYS.map((delay) => (
                        <option key={delay} value={String(delay)}>{delay}ms</option>
                    ))}
                </select>
            </label>
            <StepJump currentStep={currentStep} totalSteps={totalSteps} disabled={!canJump}
                onJump={onJump} summarize={summarizeStep} breakpointStops={breakpointStops} />
        </div>
    );
}
