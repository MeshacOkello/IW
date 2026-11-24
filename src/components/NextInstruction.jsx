import NumberText from "./NumberText";

export default function NextInstruction({
    assemblyCode,
    currentLine,
    isLoaded,
    explanation,
    explanationParts,
    formats,
    label = "Executed instruction",
}) {
    let instruction = "Load a program to begin.";

    if (isLoaded && currentLine != null) {
        const sourceLine = assemblyCode.split("\n")[currentLine - 1];

        if (sourceLine !== undefined) {
            instruction = sourceLine
                .split("//")[0]
                .replace(/^\s*(?:[\w.$]+:\s*)+/, "")
                .trim();
        } else {
            instruction = "Source line unavailable. Reload the program.";
        }
    } else if (isLoaded) {
        instruction = "Select Next for the first instruction.";
    }

    return (
        <div className="next-instruction">
            {/* The label and the instruction share a line; what the
                instruction did reads underneath them. */}
            <div className="next-instruction-head">
                <span>{label}</span>
                <h5 className="next-instruction-code" title={instruction}>{instruction}</h5>
            </div>
            <div className="next-instruction-body">
                {isLoaded && currentLine != null && explanation && (
                    <p><NumberText parts={explanationParts} fallback={explanation} formats={formats} /></p>
                )}
            </div>
        </div>
    );
}
