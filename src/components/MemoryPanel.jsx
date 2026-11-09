import Stack from "./Stack";
import Heap from "./Heap";

export default function MemoryPanel({
    stackValues,
    heapAllocations,
    frameValues,
    memoryFormat,
    setMemoryFormat,
    stackPointer,
    memoryAccesses,
}) {
    return (
        <div>
            <div className="memory-header">
                <h5>Memory</h5>

                <div className="memory-options">
                    <select
                        value={memoryFormat}
                        onChange={(event) =>
                            setMemoryFormat(event.target.value)
                        }
                    >
                        <option value="hex">Hex</option>
                        <option value="dec">Dec</option>
                    </select>
                </div>
            </div>

            <div className="memory-columns">
                <Stack
                    stackValues={stackValues}
                    frameValues={frameValues}
                    memoryFormat={memoryFormat}
                    stackPointer={stackPointer}
                    memoryAccesses={memoryAccesses}
                />
                <Heap
                    allocations={heapAllocations}
                    memoryFormat={memoryFormat}
                    memoryAccesses={memoryAccesses}
                />
            </div>
        </div>
    );
}
