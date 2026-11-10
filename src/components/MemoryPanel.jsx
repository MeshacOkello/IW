import Stack from "./Stack";
import Heap from "./Heap";
import Section from "./Section";

// .text has no visualization, and .rodata sits under the registers.
const SECTION_NAMES = [".data", ".bss"];

export default function MemoryPanel({
    stackValues,
    heapAllocations,
    frameValues,
    formats,
    stackPointer,
    memoryAccesses,
    sections,
}) {
    const layout = new Map((sections ?? []).map((section) => [section.name, section]));

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

            <div className="section-columns">
                {SECTION_NAMES.map((name) => (
                    <Section
                        key={name}
                        name={name}
                        section={layout.get(name)}
                        formats={formats}
                        memoryAccesses={memoryAccesses}
                    />
                ))}
            </div>
        </div>
    );
}
