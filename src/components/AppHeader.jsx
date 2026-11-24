import { useLayoutEffect, useRef } from "react";
import PageNav from "./PageNav";

export default function AppHeader({ current, formats, onAddressFormatChange, onDataFormatChange }) {
    const header = useRef(null);

    useLayoutEffect(() => {
        const measure = () => document.documentElement.style.setProperty(
            "--app-header-height", `${header.current.getBoundingClientRect().height}px`,
        );
        measure();
        const observer = new ResizeObserver(measure);
        observer.observe(header.current);
        return () => observer.disconnect();
    }, []);

    return (
        <header className="app-header" ref={header}>
            <a className="app-brand" href="#/" aria-label="Assembly Visualizer home">
                <span className="app-name">Assembly Visualizer</span>
            </a>
            <PageNav current={current} />
            <fieldset className="header-formats">
                <legend className="visually-hidden">Visualizer display formats</legend>
                <label>
                    Addresses
                    <select value={formats.address} onChange={event => onAddressFormatChange(event.target.value)}>
                        <option value="hex">Hex</option>
                        <option value="dec">Dec</option>
                    </select>
                </label>
                <label>
                    Data
                    <select value={formats.data} onChange={event => onDataFormatChange(event.target.value)}>
                        <option value="hex">Hex</option>
                        <option value="dec">Dec</option>
                    </select>
                </label>
            </fieldset>
        </header>
    );
}
