import MemoryFrame from "./MemoryFrame";

export default function Stack({
    stackValues,
    frameValues,
    memoryFormat = "hex",
    stackPointer,
    memoryAccesses = [],
}) {
    const cells = stackValues ?? [];
    const allFrames = frameValues ?? [];

    const frames = allFrames
        .map((frame, depth) => ({
            ...frame,
            depth,
            isActive: depth === allFrames.length - 1,
        }))
        .reverse()
        .filter((frame) => frame.stack_start < frame.stack_end);

    return (
        <div className="stack-section">
            <h5>Stack</h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Value</span>
            </div>

            <div className="stack-bar">
                {frames.map((frame) => (
                    <MemoryFrame
                        key={frame.id}
                        label={frame.depth === 0 ? frame.name : `${frame.name} #${frame.depth}`}
                        title={`${frame.name} — call depth ${frame.depth}`}
                        size={frame.stack_end - frame.stack_start}
                        colorIndex={frame.id}
                        cells={cells.filter((cell) =>
                            cell.address >= frame.stack_start && cell.address < frame.stack_end
                        )}
                        memoryFormat={memoryFormat}
                        memoryAccesses={memoryAccesses}
                        stackPointer={stackPointer}
                        isActive={frame.isActive}
                    />
                ))}
            </div>
        </div>
    );
}
