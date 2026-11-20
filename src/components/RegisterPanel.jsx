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
                <th scope="row">{label}</th>
                <td className={isAddress ? "address-value" : undefined}>
                    {formatNumber(registerValues[index], isAddress ? formats.address : formats.data)}
                </td>
            </tr>
        );
    }

    return (
        <div className="register-tables">
            {REGISTER_COLUMNS.map((column, index) => (
                <table key={index}>
                    <thead>
                        <tr>
                            <th scope="col">Reg</th>
                            <th scope="col">Value</th>
                        </tr>
                    </thead>
                    <tbody>{column.map(renderRegister)}</tbody>
                </table>
            ))}
        </div>
    );
}
