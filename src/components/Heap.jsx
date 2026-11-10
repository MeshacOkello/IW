import { formatNumber } from "../numberFormat";

const CELL_BYTES = 8;

function allocationCells(allocation, writes) {
    const { address, size, contents } = allocation;
    const cells = [];
    for (let offset = 0; offset < size; offset += CELL_BYTES) {
        const end = Math.min(size, offset + CELL_BYTES);
        const bytes = contents.slice(offset * 2, end * 2).match(/../g);
        const cellAddress = address + offset;
        cells.push({
            address: cellAddress,
            bytes,
            written: writes.some((write) =>
                write.address < address + end && cellAddress < write.address + write.size
            ),
        });
    }
    return cells;
}

function CellContents({ cell, dataFormat }) {
    const initialized = cell.bytes.filter((byte) => byte !== "??");
    if (initialized.length === 0) return "[empty]";

    // Pack the known bytes in little-endian order without padding gaps.
    const value = BigInt("0x" + initialized.reverse().join(""));
    const text = formatNumber(value, dataFormat);
    const partial = initialized.length < cell.bytes.length;
    return (
        <span title={partial ? "Only initialized bytes are included" : undefined}>
            {text}
        </span>
    );
}

export default function Heap({ allocations = [], formats, memoryAccesses = [] }) {
    const writes = memoryAccesses.filter((access) => access.kind === "write");

    return (
        <div className="heap-section">
            <h5>Heap</h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Data</span>
            </div>

            <div className="heap-bar">
                {allocations.length === 0 && <p className="heap-empty">No active allocations</p>}
                {allocations.map((allocation) => {
                    const address = formatNumber(allocation.address, formats.address);
                    return (
                        <fieldset className="memory-frame heap-allocation" key={allocation.address}>
                            <legend className="frame-header">
                                <span className="frame-heading">
                                    <span className="frame-title address-value" title={address}>{address}</span>
                                    <span className="frame-size">{formatNumber(allocation.size, formats.data)} B</span>
                                </span>
                            </legend>

                            <div className="heap-contents">
                                {allocation.size === 0 && <span>[empty]</span>}
                                {allocationCells(allocation, writes).map((cell) => (
                                    <div
                                        className={`memory-cell heap-cell${cell.written ? " memory-written" : ""}`}
                                        key={cell.address}
                                        title={formatNumber(cell.bytes.length, formats.data) + " B"}
                                    >
                                        <span className="heap-cell-address address-value">
                                            {formatNumber(cell.address, formats.address)}
                                        </span>
                                        <span className="heap-values">
                                            <CellContents cell={cell} dataFormat={formats.data} />
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </fieldset>
                    );
                })}
            </div>
        </div>
    );
}
