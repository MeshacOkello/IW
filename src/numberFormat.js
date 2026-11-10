export function formatNumber(value, format) {
    const integer = BigInt(value);
    if (format === "dec") return integer.toString();
    const magnitude = integer < 0n ? -integer : integer;
    return (integer < 0n ? "-0x" : "0x") + magnitude.toString(16).toUpperCase();
}
