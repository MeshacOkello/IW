export default function NextInstruction({
    assemblyCode,
    currentLine,
    isLoaded,
    explanation,
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
        instruction = "Click Next to execute the first instruction.";
    }

    return (
        <div className="next-instruction">
            <span>Executed Instruction</span>
            <h5>{instruction}</h5>
            {isLoaded && currentLine != null && explanation && (
                <h5>{explanation}</h5>
            )}
        </div>
    );
}
