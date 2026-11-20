// Split a line of assembly into coloured spans for the editor backdrop.
//
// The backdrop sits exactly behind the textarea, so a token may never add,
// drop or reorder a character: joining the pieces back together must give the
// original line. Every branch below consumes at least one character, and the
// final fallback consumes one, so the scan always terminates.

const SPACING = /^[ \t,[\]!{}]+/;
const STRING = /^"(?:\\.|[^"\\])*"?/;
const CHARACTER = /^'(?:\\.|[^'\\])*'?/;
const LABEL = /^[A-Za-z_.$][\w.$]*:/;
const DIRECTIVE = /^\.[A-Za-z][\w.]*/;
const MNEMONIC = /^[A-Za-z][\w.]*/;
const IMMEDIATE = /^#[-+]?(?:0[xX][0-9a-fA-F]+|\d+|'(?:\\.|[^'])*'|[A-Za-z_.$][\w.$]*)/;
const REGISTER = /^(?:[xw](?:3[01]|[12]?\d)|xzr|wzr|wsp|sp|lr|pc)(?![\w.$])/i;
const NUMBER = /^(?:0[xX][0-9a-fA-F]+|\d+)(?![\w.$])/;
const WORD = /^[A-Za-z_.$][\w.$]*/;

/** The spans one line is drawn as, in order. */
export function highlightLine(line) {
    const tokens = [];
    let index = 0;
    // Only the first word of a line names the operation; after it, a bare
    // word is a label being referred to rather than a mnemonic.
    let afterOperation = false;

    function take(length, kind) {
        tokens.push({ text: line.slice(index, index + length), kind });
        index += length;
    }

    while (index < line.length) {
        const rest = line.slice(index);
        let match;

        if (rest.startsWith("//")) {
            take(rest.length, "comment");
            break;
        }
        if ((match = SPACING.exec(rest))) {
            take(match[0].length, "plain");
        } else if ((match = STRING.exec(rest)) || (match = CHARACTER.exec(rest))) {
            take(match[0].length, "string");
        } else if (!afterOperation && (match = LABEL.exec(rest))) {
            take(match[0].length, "label");
        } else if (!afterOperation && (match = DIRECTIVE.exec(rest))) {
            afterOperation = true;
            take(match[0].length, "directive");
        } else if (!afterOperation && (match = MNEMONIC.exec(rest))) {
            afterOperation = true;
            take(match[0].length, "mnemonic");
        } else if ((match = IMMEDIATE.exec(rest))) {
            take(match[0].length, "immediate");
        } else if ((match = REGISTER.exec(rest))) {
            take(match[0].length, "register");
        } else if ((match = NUMBER.exec(rest))) {
            take(match[0].length, "number");
        } else if ((match = WORD.exec(rest))) {
            take(match[0].length, "name");
        } else {
            take(1, "plain");
        }
    }
    return tokens;
}
