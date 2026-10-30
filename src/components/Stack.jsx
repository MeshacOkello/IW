export default function Stack({stackValues, stackPointer}) {
    const startIndex = stackPointer ? (stackPointer - 0x8000) / 8 : 512;
    const activeStack = stackValues?.slice(startIndex);

    return (
        <div className="stack-section">
            <h5>Stack</h5>
            <div className="stack-bar">
                {activeStack?.map((value, index) => (
                    <div className="memory-cell" key={startIndex + index}>
                        <span>0x{(0x8000 + (startIndex + index) * 8).toString(16)}</span>
                        <span>{value}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}