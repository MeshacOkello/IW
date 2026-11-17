import NumberText from "./NumberText";
import { blamesProgram, describe, showsDetail } from "../errors";

// One presentation for every failure: what kind it is, where it happened,
// what went wrong, and what to try. A problem in the simulator or in the
// request is labelled as such, so it never reads as a mistake in the program.
export default function ErrorMessage({ error, formats }) {
    if (!error) return null;
    const { label } = describe(error.kind);
    const showsLocation = blamesProgram(error) && error.line !== null;

    return (
        <div className={`error-message error-${error.kind}`} role="alert">
            <p className="error-headline">
                <span className="error-kind">{label}</span>
                {showsLocation && <span className="error-location">Line {error.line}</span>}
            </p>
            {showsLocation && error.sourceLine && (
                <pre className="error-source"><code>{error.sourceLine}</code></pre>
            )}
            <p className="error-text">
                <NumberText parts={error.parts} fallback={error.message} formats={formats} />
            </p>
            {error.suggestion && <p className="error-suggestion">{error.suggestion}</p>}
            {showsDetail(error) && <p className="error-detail">{error.detail}</p>}
        </div>
    );
}
