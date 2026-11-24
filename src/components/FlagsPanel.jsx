import { formatNumber } from "../numberFormat";
import { ResultMark } from "./PredictFields";
import { fieldFor } from "../predict";

// The condition flags, read out of the NZCV register the trace records.
// In predict mode each flag becomes a 0/1 toggle while the student answers.
export default function FlagsPanel({ registerValues, formats, predict = null }) {
    const nzcv = registerValues?.[33] ?? 0;

    return (
        <section className="flags-panel" aria-label="Condition flags">
            <h2>NZCV</h2>
            <div className="flag-boxes">
                {[..."NZCV"].map((flag, index) => {
                    const value = (nzcv >>> (31 - index)) & 1;
                    const field = fieldFor(predict, `flag:${flag}`);
                    if (field && predict.phase === "ask") {
                        const answer = predict.answers[field.id] ?? String(field.initial);
                        return (
                            <button
                                type="button"
                                className="flag-box predict-flag"
                                key={flag}
                                aria-pressed={answer === "1"}
                                aria-label={`Predict ${flag} flag: ${answer}`}
                                data-predict-field={index === 0 ? "" : undefined}
                                onClick={() => predict.setAnswer(field.id, answer === "1" ? "0" : "1")}
                            >
                                {flag}: {answer}
                            </button>
                        );
                    }
                    return (
                        <span className={`flag-box${field ? ` predict-flag-${predict.phase}` : ""}`} key={flag}>
                            {flag}: {formatNumber(value, formats.data)}
                            <ResultMark predict={predict} field={field} formats={formats} compact />
                        </span>
                    );
                })}
            </div>
        </section>
    );
}
