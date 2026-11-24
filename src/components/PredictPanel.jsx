import { describeAnswer } from "../predict";

function missText({ field, result }, formats) {
    const given = result.status === "missing" ? "no answer"
        : result.status === "invalid" ? `“${result.given}”`
        : describeAnswer(field, result.given, formats);
    return `${field.label}: you said ${given}, answer ${describeAnswer(field, field.expected, formats)}`;
}

// The predict-mode card under the playback controls: the question, the result
// of the last check, and the score for this run.
export default function PredictPanel({ question, review, score, practice, onCheck, onSkip, formats }) {
    let body;
    if (question) {
        body = (
            <>
                <div className="predict-prompt">
                    <strong>What changes?</strong>
                    <span>Fill in the highlighted fields, then Check.</span>
                </div>
                {question.info.libraryCall && (
                    <p className="predict-note">
                        {question.info.libraryCall} runs to completion here. Its result in x0 isn’t scored.
                    </p>
                )}
                {practice && <p className="predict-note">Already scored: this one is practice.</p>}
                <div className="predict-actions">
                    <button className="primary" onClick={onCheck}>Check</button>
                    <button onClick={onSkip}>Skip / reveal</button>
                </div>
            </>
        );
    } else if (review?.revealed) {
        body = <p className="predict-result">Answer shown, not scored.</p>;
    } else if (review) {
        const wrong = review.fields.filter((field) => !review.check.results[field.id].correct);
        body = (
            <>
                <p className={`predict-result ${wrong.length ? "predict-result-wrong" : "predict-result-correct"}`}>
                    {review.check.correct} of {review.check.total} correct
                    {!review.counted && <span className="predict-note"> · practice, not scored</span>}
                </p>
                {wrong.length > 0 && (
                    <ul className="predict-misses">
                        {wrong.map((field) => (
                            <li key={field.id}>{missText({ field, result: review.check.results[field.id] }, formats)}</li>
                        ))}
                    </ul>
                )}
            </>
        );
    } else {
        body = <p className="predict-result">Select Next to predict the next instruction.</p>;
    }

    return (
        <section className="predict-panel" aria-label="Predict mode" aria-live="polite">
            <div className="predict-body">{body}</div>
            <div className="predict-score">
                <span>Score <strong>{score.correct} / {score.total}</strong> fields</span>
                {score.missed.length > 0 && (
                    <details>
                        <summary>Missed ({score.missed.length})</summary>
                        <ul className="predict-misses">
                            {[...score.missed].reverse().map((miss) => (
                                <li key={miss.step}>
                                    <span className="predict-miss-line">Line {miss.line} · <code>{miss.instruction}</code></span>
                                    <span>{miss.wrong.map((entry) => missText(entry, formats)).join("; ")}</span>
                                </li>
                            ))}
                        </ul>
                    </details>
                )}
            </div>
        </section>
    );
}
