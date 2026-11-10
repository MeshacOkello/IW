import { useEffect, useRef, useState } from "react";

// Index of the row that covers a position, by binary search over the offsets.
function rowAt(offsets, position) {
    let low = 0;
    let high = offsets.length - 2;
    while (low < high) {
        const middle = (low + high) >> 1;
        if (offsets[middle + 1] <= position) low = middle + 1;
        else high = middle;
    }
    return low;
}

// A scrollable list that renders only the rows inside the viewport, so a
// section holding thousands of memory rows stays responsive. Rows may have
// different heights; rowHeight is a number or a function of the row.
export default function VirtualRows({ rows, rowHeight, overscan = 6, renderRow, className }) {
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

    const heightOf = typeof rowHeight === "function" ? rowHeight : () => rowHeight;
    const offsets = [0];
    for (const row of rows) offsets.push(offsets[offsets.length - 1] + heightOf(row));
    const total = offsets[rows.length];

    // A shorter program can leave the viewport scrolled past its new contents,
    // so the offset is clamped to what there is to show.
    const offset = Math.min(scrollTop, Math.max(0, total - viewportHeight));
    const first = Math.max(0, rowAt(offsets, offset) - overscan);
    const last = Math.min(rows.length, rowAt(offsets, offset + viewportHeight) + 1 + overscan);

    return (
        <div
            className={className}
            ref={viewportRef}
            onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        >
            <div className="virtual-rows" style={{ height: total, paddingTop: offsets[first] }}>
                {rows.slice(first, last).map((row) => (
                    <div className="virtual-row" key={row.key} style={{ height: heightOf(row) }}>
                        {renderRow(row)}
                    </div>
                ))}
            </div>
        </div>
    );
}
