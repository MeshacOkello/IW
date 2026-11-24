import { formatNumber } from "../numberFormat";
import { describeAnswer } from "../predict";

// The pieces predict mode puts inside the Registers, NZCV and RAM panels.
// `predict` is null outside predict mode; otherwise it is
//   { phase: "ask", fields, answers, setAnswer, submit }  while asking, or
//   { phase: "review", fields, check, revealed }          after Check / Skip.

function submitOnEnter(predict) {
    return (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            predict.submit();
        }
    };
}

// What the student wrote, read back in the current format where it parsed.
function givenText(field, result, formats, isAddress) {
    if (result.status === "missing") return "no answer";
    if (result.status === "invalid") return `“${result.given}”`;
    return describeAnswer(field, result.given, formats, isAddress);
}

// `compact` drops what the student wrote, for a 0/1 flag where it is plain.
export function ResultMark({ predict, field, formats, isAddress = false, showAnswer = false, compact = false }) {
    if (predict?.phase !== "review" || !field) return null;
    if (predict.revealed) return <span className="predict-mark predict-revealed" title="Revealed, not scored">shown</span>;
    const result = predict.check.results[field.id];
    if (result.correct) return <span className="predict-mark predict-correct" title="Your prediction was right">✓</span>;
    const answer = describeAnswer(field, field.expected, formats, isAddress);
    return (
        <span className="predict-mark predict-wrong" title={`You predicted ${givenText(field, result, formats, isAddress)}; the answer is ${answer}`}>
            ✗{!compact && <> <s>{givenText(field, result, formats, isAddress)}</s></>}
            {showAnswer && <> → {answer}</>}
        </span>
    );
}

export function NumberField({ predict, field, format, label }) {
    const prefill = field.initial === undefined ? "" : formatNumber(BigInt.asUintN(64, field.initial), format);
    return (
        <input
            className="predict-input"
            data-predict-field
            value={predict.answers[field.id] ?? prefill}
            placeholder={format === "hex" ? "0x…" : "decimal"}
            onChange={(event) => predict.setAnswer(field.id, event.target.value)}
            onKeyDown={submitOnEnter(predict)}
            spellCheck={false}
            autoComplete="off"
            aria-label={label}
        />
    );
}

export function BranchChoice({ predict, field, formats }) {
    if (predict.phase === "review") {
        return (
            <span className="predict-branch-result">
                {" · "}{describeAnswer(field, field.expected, formats)}
                <ResultMark predict={predict} field={field} formats={formats} />
            </span>
        );
    }
    const answer = predict.answers[field.id];
    return (
        <span className="predict-branch" role="radiogroup" aria-label="Is the branch taken?">
            {[["taken", "Taken"], ["not-taken", "Not taken"]].map(([value, text], index) => (
                <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={answer === value}
                    data-predict-field={index === 0 ? "" : undefined}
                    className={answer === value ? "selected" : undefined}
                    onClick={() => predict.setAnswer(field.id, value)}
                    onKeyDown={(event) => {
                        if (event.key === "Enter" && answer !== undefined) {
                            event.preventDefault();
                            predict.submit();
                        }
                    }}
                >{text}</button>
            ))}
        </span>
    );
}

// The stores this instruction makes into one RAM region, each as an address
// and a value to predict.
export function PredictStores({ predict, region, formats }) {
    const fields = predict?.fields.filter((field) => field.region === region) ?? [];
    if (fields.length === 0) return null;
    const slots = [...new Set(fields.map((field) => field.slot))];
    const many = predict.fields.filter((field) => field.kind === "address").length > 1;

    return (
        <div className={`predict-stores predict-${predict.phase}`}>
            {slots.map((slot) => {
                const address = fields.find((field) => field.slot === slot && field.kind === "address");
                const value = fields.find((field) => field.slot === slot && field.kind === "value");
                const title = `${many ? `Store ${slot + 1}` : "Store"} · ${value.bytes} B`;
                return (
                    <div className="predict-store" key={slot}>
                        <span className="predict-store-title">{title}</span>
                        {predict.phase === "ask" ? (
                            <>
                                <label>Address <NumberField predict={predict} field={address} format={formats.address} label={`${title}: address`} /></label>
                                <label>Value <NumberField predict={predict} field={value} format={formats.data} label={`${title}: value`} /></label>
                            </>
                        ) : (
                            <>
                                <span className="predict-store-row">
                                    <span className="address-value">{describeAnswer(address, address.expected, formats)}</span>
                                    <ResultMark predict={predict} field={address} formats={formats} />
                                </span>
                                <span className="predict-store-row">
                                    <span>{describeAnswer(value, value.expected, formats)}</span>
                                    <ResultMark predict={predict} field={value} formats={formats} />
                                </span>
                            </>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
