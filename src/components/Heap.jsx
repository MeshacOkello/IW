import { formatNumber } from "../numberFormat";
import { cellValue, memoryCells } from "../memoryCells";

function allocationCells(allocation, writes) {
    const { address, size, contents } = allocation;
    return memoryCells(address, size, contents).map((cell) => ({
        ...cell,
        written: writes.some((write) =>
            write.address < cell.address + cell.size && cell.address < write.address + write.size
        ),
    }));
}

function CellContents({ cell, dataFormat }) {
    const value = cellValue(cell.bytes);
    if (value === null) return "[empty]";

    const text = formatNumber(value, dataFormat);
    const partial = cell.bytes.some((byte) => byte === "??");
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
                                        style={{ "--byte-count": cell.bytes.length }}
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
