// The delay automatic execution waits between instructions, in milliseconds.
export const DEFAULT_RUN_DELAY = 900;
export const MIN_RUN_DELAY = 0;
export const MAX_RUN_DELAY = 10000;

// The field holds whatever the user types; this is the delay it stands for.
// A blank or unreadable field keeps running at the default speed.
export function runDelayFrom(text) {
    const value = Number(text);
    if (String(text).trim() === "" || !Number.isFinite(value)) return DEFAULT_RUN_DELAY;
    return Math.min(Math.max(Math.round(value), MIN_RUN_DELAY), MAX_RUN_DELAY);
}
