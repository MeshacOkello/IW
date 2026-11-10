import { formatNumber } from "../numberFormat";

const REGISTER_COLUMNS = [
    Array.from({ length: 17 }, (_, index) => index),
    Array.from({ length: 16 }, (_, index) => index + 17),
];
const EMPTY_REGISTERS = Array(34).fill(0);

export default function RegisterPanel({
    registerValues = EMPTY_REGISTERS,
    previousRegisterValues,
    pointerRegisters,
    formats,
}) {
    const pointers = new Set(pointerRegisters);
    const nzcv = registerValues[33];

    function changed(index) {
        return previousRegisterValues && registerValues[index] !== previousRegisterValues[index]
            ? "register-changed"
            : "";
    }

    function renderRegister(index) {
        const isAddress = index === 31 || index === 32 || pointers.has(index);
        const label = index === 31 ? "sp" : index === 32 ? "pc" : `x${index}`;
        return (
            <tr className={changed(index)} key={index}>
                <td>{label}</td>
                <td className={isAddress ? "address-value" : undefined}>
                    {formatNumber(registerValues[index], isAddress ? formats.address : formats.data)}
                </td>
            </tr>
        );
    }

    return (
        <>
            <div className="register-header">
                <h5>Registers</h5>
                <div className="register-options">
                    <button>64-bit x</button>
                    <button>32-bit w</button>
                </div>
            </div>

            <div className="register-tables">
                <table>
                    <tbody>{REGISTER_COLUMNS[0].map(renderRegister)}</tbody>
                </table>
                <table>
                    <tbody>
                        {REGISTER_COLUMNS[1].map(renderRegister)}
                        <tr className={changed(33)}>
                            <td>NZCV</td>
                            <td>
                                <div className="nzcv-flags">
                                    {[..."NZCV"].map((flag, index) => (
                                        <span key={flag}>{flag} {formatNumber((nzcv >>> (31 - index)) & 1, formats.data)}</span>
                                    ))}
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </>
    );
}
