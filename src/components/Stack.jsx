import MemoryFrame from "./MemoryFrame";
import MemoryHeading from "./MemoryHeading";
import { PredictStores } from "./PredictFields";

export default function Stack({
    stackValues,
    frameValues,
    formats,
    stackPointer,
    memoryAccesses = [],
    predict = null,
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
            <MemoryHeading name="Stack"
                bytes={frames.reduce((total, frame) => total + frame.stack_end - frame.stack_start, 0)}
                usageDescription="Space reserved by active stack frames" />

            <PredictStores predict={predict} region="stack" formats={formats} />

            <div className="stack-labels">
                <span>Address</span>
                <span>Data</span>
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
                        formats={formats}
                        memoryAccesses={memoryAccesses}
                        stackPointer={stackPointer}
                        isActive={frame.isActive}
                    />
                ))}
            </div>
        </div>
    );
}
