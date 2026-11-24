export default function MemoryHeading({ name, bytes, title, usageDescription }) {
    return (
        <h5 className="memory-heading" title={title}>
            <span>{name}</span>
            <span className="memory-usage" title={usageDescription} aria-label={`${bytes} bytes`}>
                {bytes.toLocaleString("en-US")} B
            </span>
        </h5>
    );
}
