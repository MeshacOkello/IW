import Stack from "./Stack";
import Heap from "./Heap";

export default function MemoryPanel({
    stackValues,
    heapAllocations,
    frameValues,
    formats,
    stackPointer,
    memoryAccesses,
}) {
    return (
        <div>
            <div className="memory-header">
                <h5>Memory</h5>

            </div>

            <div className="memory-columns">
                <Stack
                    stackValues={stackValues}
                    frameValues={frameValues}
                    formats={formats}
                    stackPointer={stackPointer}
                    memoryAccesses={memoryAccesses}
                />
                <Heap
                    allocations={heapAllocations}
                    formats={formats}
                    memoryAccesses={memoryAccesses}
                />
            </div>
        </div>
    );
}
