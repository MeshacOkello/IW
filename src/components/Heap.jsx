function formatContents(allocation, writes, memoryFormat) {
    const groups = [];
    for (let offset = 0; offset < allocation.size; offset++) {
        const address = allocation.address + offset;
        const written = writes.some(({ address: start, size }) => start <= address && address < start + size);
        const hex = allocation.contents.slice(offset * 2, offset * 2 + 2);
        const byte = memoryFormat === "dec" && hex !== "??"
            ? String(parseInt(hex, 16)).padStart(3, "0")
            : hex;
        const previous = groups[groups.length - 1];
        if (previous?.written === written) {
            previous.text += " " + byte;
        } else {
            groups.push({ offset, written, text: byte });
        }
    }

    return groups.map(({ offset, written, text }) => (
        <span key={offset}>
            {offset > 0 && " "}
            {written ? <mark className="heap-written">{text}</mark> : text}
        </span>
    ));
}

export default function Heap({ allocations = [], memoryFormat = "hex", memoryAccesses = [] }) {
    const writes = memoryAccesses.filter((access) => access.kind === "write");
    return (
        <div className="heap-section">
            <h5>Heap</h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Size</span>
            </div>

            <div className="heap-bar" title="?? means the program has not written this byte">
                {allocations.length === 0 && <p className="heap-empty">No active allocations</p>}
                {allocations.map((allocation) => (
                    <div className="heap-allocation" key={allocation.address}>
                        <div className="memory-cell">
                            <span>{memoryFormat === "dec" ? allocation.address : "0x" + allocation.address.toString(16)}</span>
                            <span>{allocation.size} B</span>
                        </div>
                        <div className="heap-contents">
                            {formatContents(allocation, writes, memoryFormat)}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
