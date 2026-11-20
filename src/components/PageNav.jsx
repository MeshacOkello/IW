// The two pages of the app. Both are hash routes, so the browser's back
// button moves between them and the workspace is never reloaded.
export default function PageNav({ current }) {
    return (
        <nav className="page-nav" aria-label="Pages">
            <a href="#/" aria-current={current === "visualizer" ? "page" : undefined}>Visualizer</a>
            <a href="#/how-to" aria-current={current === "guide" ? "page" : undefined}>How to use</a>
        </nav>
    );
}
