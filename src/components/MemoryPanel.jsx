import Stack from "./Stack";
import Heap from "./Heap";
import Section from "./Section";
import { PredictStores } from "./PredictFields";

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
    predict = null,
}) {
    const layout = new Map((sections ?? []).map((section) => [section.name, section]));

    return (
        <>
        {/* A store outside every region shown below still gets asked about. */}
        <PredictStores predict={predict} region="memory" formats={formats} />
        <div className="ram-grid">
            <Stack
                stackValues={stackValues}
                frameValues={frameValues}
                formats={formats}
                stackPointer={stackPointer}
                memoryAccesses={memoryAccesses}
                predict={predict}
            />
            <Heap
                allocations={heapAllocations}
                formats={formats}
                memoryAccesses={memoryAccesses}
                predict={predict}
            />
            {SECTION_NAMES.map((name) => (
                <Section
                    key={name}
                    name={name}
                    section={layout.get(name)}
                    formats={formats}
                    memoryAccesses={memoryAccesses}
                    predict={predict}
                />
            ))}
        </div>
        </>
    );
}
