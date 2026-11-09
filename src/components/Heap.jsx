import MemoryFrame from "./MemoryFrame";

const SLOT_BYTES = 8;

function memoryCells(allocation, writes, memoryFormat) {
    const { address, size, contents } = allocation;
    const writtenBytes = new Uint8Array(size);
    for (const write of writes) {
        const start = Math.max(0, write.address - address);
        const end = Math.min(size, write.address + write.size - address);
        if (start < end) writtenBytes.fill(1, start, end);
    }

    const byteAt = (offset) => contents.slice(offset * 2, offset * 2 + 2);
    const cells = [];
    let offset = 0;
    while (offset < size) {
        const start = offset;
        const cellAddress = address + start;
        const initialized = byteAt(start) !== "??";
        const written = writtenBytes[start];
        const slotEnd = Math.min(size, start + SLOT_BYTES - (cellAddress % SLOT_BYTES));

        // Split at slot boundaries, gaps in initialization, and write edges.
        // A partial write then highlights only the bytes it touched.
        let littleEndianHex = "";
        while (
            offset < slotEnd &&
            (byteAt(offset) !== "??") === initialized &&
            writtenBytes[offset] === written
        ) {
            if (initialized) littleEndianHex = byteAt(offset) + littleEndianHex;
            offset++;
        }
        const value = initialized ? "0x" + littleEndianHex : null;
        cells.push({
            address: cellAddress,
            size: offset - start,
            value: value !== null && memoryFormat === "dec" ? BigInt(value).toString() : value,
            written: Boolean(written),
        });
    }
    return cells;
}

export default function Heap({ allocations = [], memoryFormat = "hex", memoryAccesses = [] }) {
    const writes = memoryAccesses.filter((access) => access.kind === "write");
    return (
        <div className="heap-section">
            <h5>Heap</h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Value</span>
            </div>

            <div className="heap-bar">
                {allocations.length === 0 && <p className="heap-empty">No active allocations</p>}
                {allocations.map((allocation) => {
                    const address = memoryFormat === "hex"
                        ? "0x" + allocation.address.toString(16)
                        : allocation.address.toString(10);
                    return (
                        <MemoryFrame
                            key={allocation.address}
                            label={address}
                            title={address}
                            size={allocation.size}
                            colorIndex={allocation.address}
                            cells={memoryCells(allocation, writes, memoryFormat)}
                            memoryFormat={memoryFormat}
                        />
                    );
                })}
            </div>
        </div>
    );
}
