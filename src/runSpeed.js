// The delay automatic execution waits between instructions, in milliseconds.
export const DEFAULT_RUN_DELAY = 900;
export const MIN_RUN_DELAY = 0;
export const MAX_RUN_DELAY = 10000;

// The speeds the toolbar offers, from as fast as the browser will repaint to
// slow enough to read each step.
export const RUN_DELAYS = [0, 100, 250, 500, 900, 1500, 3000, 5000];

// The control holds whatever was chosen; this is the delay it stands for.
// A blank or unreadable value keeps running at the default speed.
export function runDelayFrom(text) {
    const value = Number(text);
    if (String(text).trim() === "" || !Number.isFinite(value)) return DEFAULT_RUN_DELAY;
    return Math.min(Math.max(Math.round(value), MIN_RUN_DELAY), MAX_RUN_DELAY);
}
