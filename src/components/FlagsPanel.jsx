import { formatNumber } from "../numberFormat";

// The condition flags, read out of the NZCV register the trace records.
export default function FlagsPanel({ registerValues, formats }) {
    const nzcv = registerValues?.[33] ?? 0;

    return (
        <section className="flags-panel" aria-label="Condition flags">
            <h2>NZCV</h2>
            <div className="flag-boxes">
                {[..."NZCV"].map((flag, index) => (
                    <span className="flag-box" key={flag}>
                        {flag}: {formatNumber((nzcv >>> (31 - index)) & 1, formats.data)}
                    </span>
                ))}
            </div>
        </section>
    );
}
