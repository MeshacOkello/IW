import { useState } from "react";

export default function RegisterPanel({registerValues, previousRegisterValues}) {

    if (registerValues == null) {
        registerValues = Array(34).fill(0);
    }

    const [numberFormat, setNumberFormat] = useState('dec');
    
    function formatValue(value) {
        if (numberFormat == 'hex') {
            value = "0x" + value.toString(16)
        }
        else {
            value = value.toString(10);
        }
        return value;
    }

    function handleNumberFormatChange(event) {
        setNumberFormat(event.target.value);
    }
    const nzcv = registerValues[33];
    const n = (nzcv >>> 31) & 1;
    const z = (nzcv >>> 30) & 1;
    const c = (nzcv >>> 29) & 1;
    const v = (nzcv >>> 28) & 1;

    return(
        <>
            <div className="register-header">
                <h5>Registers</h5>
                <div className="register-options">
                    <button>64-bit x</button>
                    <button>32-bit w</button>
                    <select value={numberFormat} onChange={handleNumberFormatChange}>
                        <option value='hex'>Hex</option>
                        <option value='dec'>Dec</option>
                    </select>
                </div>
            </div>
            
            <div className="register-tables">
                <table>
                    <tbody>
                    <tr className={previousRegisterValues && registerValues[0] !== previousRegisterValues[0] ? "register-changed" : ""}>
                        <td>x0</td>
                        <td>{formatValue(registerValues[0])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[1] !== previousRegisterValues[1] ? "register-changed" : ""}>
                        <td>x1</td>
                        <td>{formatValue(registerValues[1])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[2] !== previousRegisterValues[2] ? "register-changed" : ""}>
                        <td>x2</td>
                        <td>{formatValue(registerValues[2])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[3] !== previousRegisterValues[3] ? "register-changed" : ""}>
                        <td>x3</td>
                        <td>{formatValue(registerValues[3])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[4] !== previousRegisterValues[4] ? "register-changed" : ""}>
                        <td>x4</td>
                        <td>{formatValue(registerValues[4])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[5] !== previousRegisterValues[5] ? "register-changed" : ""}>
                        <td>x5</td>
                        <td>{formatValue(registerValues[5])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[6] !== previousRegisterValues[6] ? "register-changed" : ""}>
                        <td>x6</td>
                        <td>{formatValue(registerValues[6])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[7] !== previousRegisterValues[7] ? "register-changed" : ""}>
                        <td>x7</td>
                        <td>{formatValue(registerValues[7])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[8] !== previousRegisterValues[8] ? "register-changed" : ""}>
                        <td>x8</td>
                        <td>{formatValue(registerValues[8])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[9] !== previousRegisterValues[9] ? "register-changed" : ""}>
                        <td>x9</td>
                        <td>{formatValue(registerValues[9])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[10] !== previousRegisterValues[10] ? "register-changed" : ""}>
                        <td>x10</td>
                        <td>{formatValue(registerValues[10])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[11] !== previousRegisterValues[11] ? "register-changed" : ""}>
                        <td>x11</td>
                        <td>{formatValue(registerValues[11])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[12] !== previousRegisterValues[12] ? "register-changed" : ""}>
                        <td>x12</td>
                        <td>{formatValue(registerValues[12])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[13] !== previousRegisterValues[13] ? "register-changed" : ""}>
                        <td>x13</td>
                        <td>{formatValue(registerValues[13])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[14] !== previousRegisterValues[14] ? "register-changed" : ""}>
                        <td>x14</td>
                        <td>{formatValue(registerValues[14])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[15] !== previousRegisterValues[15] ? "register-changed" : ""}>
                        <td>x15</td>
                        <td>{formatValue(registerValues[15])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[16] !== previousRegisterValues[16] ? "register-changed" : ""}>
                        <td>x16</td>
                        <td>{formatValue(registerValues[16])}</td>
                    </tr>
                    
                    </tbody>
                    </table> 
                    <table>
                        <tbody>
                            
                            <tr className={previousRegisterValues && registerValues[17] !== previousRegisterValues[17] ? "register-changed" : ""}>
                        <td>x17</td>
                        <td>{formatValue(registerValues[17])}</td>
                       
                    </tr>
                    <tr className={previousRegisterValues && registerValues[18] !== previousRegisterValues[18] ? "register-changed" : ""}>
                        <td>x18</td>
                        <td>{formatValue(registerValues[18])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[19] !== previousRegisterValues[19] ? "register-changed" : ""}>
                        <td>x19</td>
                        <td>{formatValue(registerValues[19])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[20] !== previousRegisterValues[20] ? "register-changed" : ""}>
                        <td>x20</td>
                        <td>{formatValue(registerValues[20])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[21] !== previousRegisterValues[21] ? "register-changed" : ""}>
                        <td>x21</td>
                        <td>{formatValue(registerValues[21])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[22] !== previousRegisterValues[22] ? "register-changed" : ""}>
                        <td>x22</td>
                        <td>{formatValue(registerValues[22])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[23] !== previousRegisterValues[23] ? "register-changed" : ""}>
                        <td>x23</td>
                        <td>{formatValue(registerValues[23])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[24] !== previousRegisterValues[24] ? "register-changed" : ""}>
                        <td>x24</td>
                        <td>{formatValue(registerValues[24])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[25] !== previousRegisterValues[25] ? "register-changed" : ""}>
                        <td>x25</td>
                        <td>{formatValue(registerValues[25])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[26] !== previousRegisterValues[26] ? "register-changed" : ""}>
                        <td>x26</td>
                        <td>{formatValue(registerValues[26])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[27] !== previousRegisterValues[27] ? "register-changed" : ""}>
                        <td>x27</td>
                        <td>{formatValue(registerValues[27])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[28] !== previousRegisterValues[28] ? "register-changed" : ""}>
                        <td>x28</td>
                        <td>{formatValue(registerValues[28])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[29] !== previousRegisterValues[29] ? "register-changed" : ""}>
                        <td>x29</td>
                        <td>{formatValue(registerValues[29])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[30] !== previousRegisterValues[30] ? "register-changed" : ""}>
                        <td>x30</td>
                        <td>{formatValue(registerValues[30])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[31] !== previousRegisterValues[31] ? "register-changed" : ""}>
                        <td>sp</td>
                        <td>{formatValue(registerValues[31])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[32] !== previousRegisterValues[32] ? "register-changed" : ""}>
                        <td>pc</td>
                        <td>{formatValue(registerValues[32])}</td>
                    </tr>
                    <tr className={previousRegisterValues && registerValues[33] !== previousRegisterValues[33] ? "register-changed" : ""}>
                        <td>NZCV</td>
                        <td>
                            <div className="nzcv-flags">
                                <span>N {n}</span> 
                                <span>Z {z}</span>
                                <span>C {c}</span>
                                <span>V {v}</span>
                            </div>
                        </td>
                    </tr>
                    
                    </tbody>
                </table>
            </div>
        </>
    );
}