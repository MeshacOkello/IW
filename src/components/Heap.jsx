import MemoryHeading from "./MemoryHeading";
import VirtualRows from "./VirtualRows";
import { formatNumber } from "../numberFormat";
import { CELL_BYTES, cellValue, memoryCells } from "../memoryCells";
import { PredictStores } from "./PredictFields";

// An allocation with more rows than this scrolls within its own box and
// renders only the rows in view, so a large block such as a 256 KiB array
// does not put tens of thousands of rows on the page at every step.
const MAX_PLAIN_CELLS = 256;
const CELL_HEIGHT = 20;

function isWritten(cell, writes) {
    return writes.some((write) =>
        write.address < cell.address + cell.size && cell.address < write.address + write.size
    );
}

function allocationCells(allocation, writes) {
    const { address, size, contents } = allocation;
    return memoryCells(address, size, contents).map((cell) => ({
        ...cell,
        written: isWritten(cell, writes),
    }));
}

// The row at `index`, read straight from the allocation's contents.
function cellAt(allocation, index, writes) {
    const offset = index * CELL_BYTES;
    const end = Math.min(allocation.size, offset + CELL_BYTES);
    const cell = {
        address: allocation.address + offset,
        size: end - offset,
        bytes: allocation.contents.slice(offset * 2, end * 2).match(/../g) ?? [],
    };
    return { ...cell, written: isWritten(cell, writes) };
}

function HeapCell({ cell, formats }) {
    return (
        <div
            className={`memory-cell heap-cell${cell.written ? " memory-written" : ""}`}
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
    );
}

function AllocationContents({ allocation, writes, formats }) {
    const count = Math.ceil(allocation.size / CELL_BYTES);
    if (count <= MAX_PLAIN_CELLS) {
        return (
            <div className="heap-contents">
                {allocation.size === 0 && <span>[empty]</span>}
                {allocationCells(allocation, writes).map((cell) => (
                    <HeapCell cell={cell} formats={formats} key={cell.address} />
                ))}
            </div>
        );
    }
    const rows = Array.from({ length: count }, (_, index) => ({ key: index, index }));
    return (
        <VirtualRows
            className="heap-contents heap-contents-scroll"
            rows={rows}
            rowHeight={CELL_HEIGHT}
            renderRow={(row) => <HeapCell cell={cellAt(allocation, row.index, writes)} formats={formats} />}
        />
    );
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

export default function Heap({ allocations = [], formats, memoryAccesses = [], predict = null }) {
    const writes = memoryAccesses.filter((access) => access.kind === "write");

    return (
        <div className="heap-section">
            <MemoryHeading name="Heap"
                bytes={allocations.reduce((total, allocation) => total + allocation.size, 0)}
                usageDescription="Total size of active allocations, including unwritten bytes" />

            <PredictStores predict={predict} region="heap" formats={formats} />

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

                            <AllocationContents allocation={allocation} writes={writes} formats={formats} />
                        </fieldset>
                    );
                })}
            </div>
        </div>
    );
}
