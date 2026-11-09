const PIXELS_PER_BYTE = 2.6;

export default function MemoryFrame({
    label,
    title,
    size,
    colorIndex,
    cells,
    memoryFormat,
    memoryAccesses = [],
    stackPointer,
    isActive = false,
}) {
    const hue = (colorIndex * 137.508) % 360;

    function formatAddress(address) {
        return memoryFormat === "hex" ? "0x" + address.toString(16) : address.toString(10);
    }

    return (
        <fieldset
            className={`memory-frame${isActive ? " active-frame" : ""}`}
            style={{
                "--frame-color": `hsl(${hue}, 55%, 35%)`,
                "--frame-background": `hsl(${hue}, 65%, 93%)`,
            }}
        >
            <legend className="frame-header">
                <span className="frame-heading">
                    <span className="frame-title" title={title}>{label}</span>
                    <span className="frame-size">{size} B</span>
                </span>
            </legend>

            <div className="frame-cells" style={{ height: size * PIXELS_PER_BYTE }}>
                {cells.map((cell) => {
                    const written = cell.written ?? memoryAccesses.some(
                        (access) =>
                            access.kind === "write" &&
                            access.address < cell.address + cell.size &&
                            cell.address < access.address + access.size
                    );
                    const address = formatAddress(cell.address);
                    const value = cell.value ?? "[empty]";
                    return (
                        <div
                            className={`memory-cell${written ? " memory-written" : ""}`}
                            key={cell.address}
                            style={{ height: cell.size * PIXELS_PER_BYTE }}
                            title={`${address} · ${cell.size} B · ${value}`}
                        >
                            <span className="stack-address">
                                {cell.address === stackPointer && (
                                    <span className="sp-marker" title="Stack pointer">SP →</span>
                                )}
                                {address}
                            </span>
                            <span>{value}</span>
                        </div>
                    );
                })}
            </div>
        </fieldset>
    );
}
