import { useLayoutEffect, useRef } from "react";

export default function StdOut({ output = "" }) {
    const element = useRef(null);
    const following = useRef(true);

    useLayoutEffect(() => {
        if (following.current) element.current.scrollTop = element.current.scrollHeight;
    }, [output]);

    function onScroll() {
        const { scrollTop, scrollHeight, clientHeight } = element.current;
        following.current = scrollHeight - scrollTop - clientHeight < 4;
    }

    return (
        <section className="stdout" aria-label="Stdout">
            <h5>Stdout</h5>
            <pre ref={element} onScroll={onScroll} aria-label="Program output">
                {output || <span className="stdout-empty">No output yet</span>}
            </pre>
        </section>
    );
}
