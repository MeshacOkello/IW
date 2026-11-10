import { formatNumber } from "../numberFormat";

export default function MemoryFrame({
    label,
    title,
    size,
    colorIndex,
    cells,
    formats,
    memoryAccesses = [],
    stackPointer,
    isActive = false,
}) {
    const hue = (colorIndex * 137.508) % 360;

    return (
        <fieldset
            className={`memory-frame${isActive ? " active-frame" : ""}`}
            style={{
                "--frame-color": `light-dark(hsl(${hue}, 55%, 35%), hsl(${hue}, 55%, 72%))`,
                "--frame-background": `light-dark(hsl(${hue}, 65%, 93%), hsl(${hue}, 25%, 19%))`,
            }}
        >
            <legend className="frame-header">
                <span className="frame-heading">
                    <span className="frame-title" title={title}>{label}</span>
                    <span className="frame-size">{formatNumber(size, formats.data)} B</span>
                </span>
            </legend>

            <div className="frame-cells" style={{ "--byte-count": size }}>
                {cells.map((cell) => {
                    const written = cell.written ?? memoryAccesses.some(
                        (access) =>
                            access.kind === "write" &&
                            access.address < cell.address + cell.size &&
                            cell.address < access.address + access.size
                    );
                    const address = formatNumber(cell.address, formats.address);
                    const value = cell.value == null ? "[empty]" : formatNumber(cell.value, formats.data);
                    return (
                        <div
                            className={`memory-cell${written ? " memory-written" : ""}`}
                            key={cell.address}
                            style={{ "--byte-count": cell.size }}
                            title={`${address} · ${formatNumber(cell.size, formats.data)} B · ${value}`}
                        >
                            <span className="stack-address">
                                {cell.address === stackPointer && (
                                    <span className="sp-marker" title="Stack pointer">SP →</span>
                                )}
                                <span className="address-value">{address}</span>
                            </span>
                            <span>{value}</span>
                        </div>
                    );
                })}
            </div>
        </fieldset>
    );
}
