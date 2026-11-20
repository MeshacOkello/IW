import Stack from "./Stack";
import Heap from "./Heap";
import Section from "./Section";

// .text holds code rather than data, so it has no visualization here.
// Every region is laid out at once: the panel never scrolls, and a region
// with more rows than it can show scrolls inside itself.
const SECTION_NAMES = [".data", ".bss", ".rodata"];

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
        <div className="ram-grid">
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
    );
}
