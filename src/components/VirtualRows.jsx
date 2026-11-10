import { useEffect, useRef, useState } from "react";

// A scrollable list that renders only the rows inside the viewport, so a
// section holding thousands of memory rows stays responsive.
export default function VirtualRows({ rows, rowHeight, overscan = 8, renderRow, className }) {
    const viewportRef = useRef(null);
    const [scrollTop, setScrollTop] = useState(0);
    const [viewportHeight, setViewportHeight] = useState(0);

    useEffect(() => {
        const viewport = viewportRef.current;
        if (!viewport) return;
        const observer = new ResizeObserver(([entry]) => setViewportHeight(entry.contentRect.height));
        observer.observe(viewport);
        return () => observer.disconnect();
    }, []);

    // A shorter program can leave the viewport scrolled past its new contents,
    // so the offset is clamped to what there is to show.
    const offset = Math.min(scrollTop, Math.max(0, rows.length * rowHeight - viewportHeight));
    const first = Math.max(0, Math.floor(offset / rowHeight) - overscan);
    const last = Math.min(rows.length, Math.ceil((offset + viewportHeight) / rowHeight) + overscan);

    return (
        <div
            className={className}
            ref={viewportRef}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
            <div
                className="virtual-rows"
                style={{ height: rows.length * rowHeight, paddingTop: first * rowHeight }}
            >
                {rows.slice(first, last).map((row) => (
                    <div className="virtual-row" key={row.key} style={{ height: rowHeight }}>
                        {renderRow(row)}
                    </div>
                ))}
            </div>
        </div>
    );
}
