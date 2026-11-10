import { formatNumber } from "../numberFormat";
import { cellValue, memoryCells } from "../memoryCells";
import VirtualRows from "./VirtualRows";

const ROW_HEIGHT = 22;
const ESCAPES = { 0: "\\0", 9: "\\t", 10: "\\n", 13: "\\r", 34: '\\"', 92: "\\\\" };

// Bytes a string directive produced read as text, with whatever cannot be
// printed shown as an escape.
function cellText(bytes) {
    return bytes
        .map((hex) => {
            const byte = parseInt(hex, 16);
            if (ESCAPES[byte] !== undefined) return ESCAPES[byte];
            return byte >= 0x20 && byte < 0x7f ? String.fromCharCode(byte) : `\\x${hex}`;
        })
        .join("");
}

// Interleave the section's labels with its memory rows so each row of bytes
// sits under the symbol it belongs to.
function sectionRows(symbols, cells) {
    const sorted = [...symbols].sort((first, second) => first.address - second.address);
    const rows = [];
    let next = 0;

    function addLabels(limit) {
        while (next < sorted.length && (limit === null || sorted[next].address < limit)) {
            rows.push({ kind: "label", key: `label-${sorted[next].name}`, symbol: sorted[next] });
            next += 1;
        }
    }

    for (const cell of cells) {
        addLabels(cell.address + cell.size);
        rows.push({ kind: "cell", key: `cell-${cell.address}`, cell });
    }
    addLabels(null);
    return rows;
}

export default function Section({ name, section, formats, memoryAccesses = [] }) {
    const { address = 0, size = 0, symbols = [], strings = [], contents = "" } = section ?? {};
    const cells = memoryCells(address, size, contents);
    const rows = sectionRows(symbols, cells);
    const writes = memoryAccesses.filter((access) => access.kind === "write");

    function renderRow(row) {
        if (row.kind === "label") {
            const labelAddress = formatNumber(row.symbol.address, formats.address);
            return (
                <span className="section-label" title={`${row.symbol.name} at ${labelAddress}`}>
                    {row.symbol.name}
                </span>
            );
        }

        const { cell } = row;
        const written = writes.some(
            (write) =>
                write.address < cell.address + cell.size &&
                cell.address < write.address + write.size
        );
        const cellAddress = formatNumber(cell.address, formats.address);
        const number = formatNumber(cellValue(cell.bytes) ?? 0, formats.data);
        // A row reads as text when it starts inside a string, so numbers next
        // to a string are still shown as numbers.
        const isText = strings.some(([start, end]) => cell.address >= start && cell.address < end);
        const value = isText ? `"${cellText(cell.bytes)}"` : number;
        return (
            <div
                className={`memory-cell section-cell${written ? " memory-written" : ""}`}
                title={`${cellAddress} · ${formatNumber(cell.size, formats.data)} B · ${isText ? `${value} · ` : ""}${number}`}
            >
                <span className="address-value">{cellAddress}</span>
                <span className={isText ? "section-string" : undefined}>{value}</span>
            </div>
        );
    }

    return (
        <div className="section-region">
            <h5 title={size ? `${name} · ${formatNumber(address, formats.address)} · ${formatNumber(size, formats.data)} B` : `${name} · empty`}>
                {name}
            </h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Data</span>
            </div>

            {rows.length === 0 ? (
                <div className="section-bar">
                    <p className="heap-empty">No {name} data</p>
                </div>
            ) : (
                <VirtualRows
                    className="section-bar"
                    rows={rows}
                    rowHeight={ROW_HEIGHT}
                    renderRow={renderRow}
                />
            )}
        </div>
    );
}
