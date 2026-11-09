const PIXELS_PER_BYTE = 2.6;

export default function Stack({
    stackValues,
    frameValues,
    memoryFormat = "hex",
    stackPointer,
    memoryAccesses = [],
}) {
    const cells = stackValues ?? [];
    const allFrames = frameValues ?? [];

    const frames = allFrames
        .map((frame, depth) => ({
            ...frame,
            depth,
            isActive: depth === allFrames.length - 1,
        }))
        .reverse()
        .filter((frame) => frame.stack_start < frame.stack_end);

    function formatAddress(address) {
        return memoryFormat === "hex"
            ? "0x" + address.toString(16)
            : address.toString(10);
    }
    function wasWritten(cell) {
    return memoryAccesses.some(
        (access) =>
            access.kind === "write" &&
            access.address < cell.address + cell.size &&
            cell.address < access.address + access.size
    );
}

    return (
        <div className="stack-section">
            <h5>Stack</h5>

            <div className="stack-labels">
                <span>Address</span>
                <span>Value</span>
            </div>

            <div className="stack-bar">
                {frames.map((frame) => {
                    const size = frame.stack_end - frame.stack_start;
                    const hue = (frame.id * 137.508) % 360;
                    const label = frame.depth === 0
                                    ? frame.name
                                    : `${frame.name} #${frame.depth}`;

                    const frameCells = cells.filter(
                        (cell) =>
                            cell.address >= frame.stack_start &&
                            cell.address < frame.stack_end
                    );

                    return (
                        <fieldset
                            className={`stack-frame${
                                frame.isActive ? " active-frame" : ""
                            }`}
                            key={frame.id}
                            style={{
                                "--frame-color": `hsl(${hue}, 55%, 35%)`,
                                "--frame-background": `hsl(${hue}, 65%, 93%)`,
                            }}
                        >
                            <legend className="frame-header">
                                <span className="frame-heading">
                                <span
                                    className="frame-title"
                                    title={`${frame.name} — call depth ${frame.depth}`}
                                >
                                    {label}
                                </span>

                                    <span className="frame-size">
                                        {size} B
                                    </span>
                                </span>
                            </legend>

                            <div
                                className="frame-cells"
                                style={{
                                    height: size * PIXELS_PER_BYTE,
                                }}
                            >
                                {frameCells.map((cell) => (
                                    <div
                                        className={`memory-cell${wasWritten(cell) ? " memory-written" : ""}`}
                                        key={cell.address}
                                        style={{
                                            height:
                                                cell.size * PIXELS_PER_BYTE,
                                        }}
                                    >
                                        <span className="stack-address">
                                            {cell.address === stackPointer && (
                                                <span
                                                    className="sp-marker"
                                                    title="Stack pointer"
                                                >
                                                    SP →
                                                </span>
                                            )}

                                            {formatAddress(cell.address)}
                                        </span>

                                        <span>
                                            {cell.value ?? "[empty]"}
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
