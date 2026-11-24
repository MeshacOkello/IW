import { formatNumber } from "../numberFormat";
import { BranchChoice, NumberField, ResultMark } from "./PredictFields";
import { fieldFor } from "../predict";

const REGISTER_COLUMNS = [
    Array.from({ length: 17 }, (_, index) => index),
    Array.from({ length: 16 }, (_, index) => index + 17),
];
const EMPTY_REGISTERS = Array(34).fill(0);

export default function RegisterPanel({
    registerValues = EMPTY_REGISTERS,
    previousRegisterValues,
    pointerRegisters,
    touchedRegisters = new Set(),
    formats,
    predict = null,
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
        const changeClass = changed(index);
        const untouchedClass = index < 31 && !touchedRegisters.has(index) && BigInt(registerValues[index]) === 0n
            ? "register-untouched" : "";
        const format = isAddress ? formats.address : formats.data;
        const field = fieldFor(predict, `reg:${index}`);
        const branch = index === 32 ? fieldFor(predict, "branch") : null;
        const predictClass = field || branch ? `register-predict register-predict-${predict.phase}` : "";
        let value = <span className="register-value">{formatNumber(registerValues[index], format)}</span>;
        if (predict?.phase === "ask" && field) {
            value = <NumberField predict={predict} field={field} format={format} label={`Predict ${field.label}`} />;
        } else if (branch) {
            const choice = <BranchChoice predict={predict} field={branch} formats={formats} />;
            value = predict.phase === "ask" ? choice : <>{value}{choice}</>;
        } else if (field) {
            value = <>{value}<ResultMark predict={predict} field={field} formats={formats} isAddress={isAddress} /></>;
        }
        return (
            <tr className={`${changeClass} ${untouchedClass} ${predictClass}`.trim()} key={index}>
                <th scope="row">{field && field.bits === 32 ? <>{label}<span className="register-width"> (w{index})</span></> : label}</th>
                <td className={isAddress && !(branch && predict.phase === "ask") ? "address-value" : undefined}
                    title={changeClass && !predictClass ? "Changed by this instruction" : undefined}>
                    {value}
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
