export default function NextInstruction() {
    return(
        <div className="next-instruction">
            <span >Next Instruction</span>
            <h5 id = 'nextInstruction'>ldr x2, [sp]</h5>
            <h5>Load 8 bytes from address in sp into x2.</h5>
        </div>
    );
}