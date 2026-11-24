// The editor's dark mode switch. The choice is remembered per browser, and
// until one is made the editor follows the system setting.
const STORAGE_KEY = "assembly-visualizer-theme";

function stored() {
    try {
        return localStorage.getItem(STORAGE_KEY);
    } catch {
        return null;   // private browsing, or storage turned off
    }
}

export function initialTheme() {
    const saved = stored();
    if (saved === "dark" || saved === "light") return saved;
    return typeof matchMedia === "function"
        && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    try {
        localStorage.setItem(STORAGE_KEY, theme);
    } catch {
        // Remembering the choice is a convenience, not a requirement.
    }
}
