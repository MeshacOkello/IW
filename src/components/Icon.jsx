// Small line icons drawn in the current text colour.
const PATHS = {
    copy: "M8 8h11v13H8z M5 16H4V3h11v1",
    check: "M5 12.5l4.5 4.5L19 7.5",
    open: "M14 4h6v6 M20 4l-9 9 M18 14v6H4V6h6",
    back: "M19 12H5 M11 6l-6 6 6 6",
};

export default function Icon({ name }) {
    return (
        <svg className="icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false">
            <path d={PATHS[name]} fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round" />
        </svg>
    );
}
