import Stack from "./Stack";
import Heap from "./Heap";

export default function MemoryPanel({stackValues, stackPointer}) {
    return(
        <div>
            <div className="memory-header">
            <h5>Memory</h5>
                <div className="memory-options">
                    <select>
                        <option>Hex</option>
                        <option>Dec</option>
                    </select>
                </div>
            </div>
            <div className="memory-columns">
                <Stack stackValues={stackValues} stackPointer={stackPointer}/>
                <Heap/>
            </div>
        </div>
    );
}