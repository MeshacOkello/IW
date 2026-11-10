export const CELL_BYTES = 8;

// Hex memory contents, split into the 8-byte rows the stack and heap show.
// A byte whose value is unknown is marked "??".
export function memoryCells(address, size, contents) {
    const cells = [];
    for (let offset = 0; offset < size; offset += CELL_BYTES) {
        const end = Math.min(size, offset + CELL_BYTES);
        cells.push({
            address: address + offset,
            size: end - offset,
            bytes: contents.slice(offset * 2, end * 2).match(/../g) ?? [],
        });
    }
    return cells;
}

// Pack the known bytes in little-endian order without padding gaps.
export function cellValue(bytes) {
    const known = bytes.filter((byte) => byte !== "??");
    if (known.length === 0) return null;
    return BigInt("0x" + [...known].reverse().join(""));
}
