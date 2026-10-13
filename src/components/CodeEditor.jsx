export default function CodeEditor() {
    const sampleCode = "mov x1, #20\nmov x2, #5\nadd x3, x1, x2";

    return(
        <div className="code-editor">
            <h4>Assembly Code</h4>
            <textarea className="assembly-input" defaultValue={sampleCode} rows={10}></textarea>
        </div>
    );
}