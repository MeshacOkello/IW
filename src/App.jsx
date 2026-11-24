import { useEffect, useRef, useState } from "react";
import AssemblyVisualizer from "./components/AssemblyVisualizer";
import HowToUse from "./components/HowToUse";
import AppHeader from "./components/AppHeader";
import { SECTIONS } from "./guide/sections";
import './App.css';

// "#/how-to" and "#/how-to/<section>" are the guide; anything else is the
// Visualizer. Hash routes need no server support and keep browser history.
function routeFrom(hash) {
    const match = /^#\/how-to(?:\/([\w-]+))?\/?$/.exec(hash);
    if (!match) return { page: "visualizer", section: null };
    const section = SECTIONS.some(({ id }) => id === match[1]) ? match[1] : null;
    return { page: "guide", section };
}

export default function App() {
    const [route, setRoute] = useState(() => routeFrom(window.location.hash));
    const workspace = useRef(null);
    const [addressFormat, setAddressFormat] = useState("hex");
    const [dataFormat, setDataFormat] = useState("dec");
    const formats = { address: addressFormat, data: dataFormat };

    useEffect(() => {
        const update = () => setRoute(routeFrom(window.location.hash));
        window.addEventListener("hashchange", update);
        return () => window.removeEventListener("hashchange", update);
    }, []);

    useEffect(() => {
        document.title = route.page === "guide" ? "How to use · Assembly Visualizer" : "Assembly Visualizer";
    }, [route.page]);

    function openExample(example) {
        workspace.current.openProgram(example.source, example.title);
        window.location.hash = "#/";
    }

    return (
        <>
            <AppHeader current={route.page === "guide" ? "guide" : "visualizer"}
                formats={formats} onAddressFormatChange={setAddressFormat} onDataFormatChange={setDataFormat} />
            {/* Kept mounted while the guide shows, so the code, the run and
                the selected step are all still there on the way back. */}
            <div hidden={route.page !== "visualizer"}>
                <AssemblyVisualizer ref={workspace} active={route.page === "visualizer"} formats={formats} />
            </div>
            {route.page === "guide" && (
                <HowToUse
                    section={route.section}
                    hasUnsavedCode={(source) => workspace.current?.hasUnsavedCode(source) ?? false}
                    onOpenExample={openExample}
                />
            )}
        </>
    );
}
