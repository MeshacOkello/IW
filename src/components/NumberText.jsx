import { formatNumber } from "../numberFormat";

export default function NumberText({ parts, fallback, formats }) {
    if (!parts) return fallback;
    return parts.map((part, index) => typeof part === "string" ? part : (
        <span key={index} className={part.kind === "address" ? "address-value" : undefined}>
            {formatNumber(part.value, formats[part.kind])}
        </span>
    ));
}
