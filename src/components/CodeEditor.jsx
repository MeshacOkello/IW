export default function CodeEditor({assemblyCode, setAssemblyCode}) {
    const sampleCode = assemblyCode

    function handleAssemblyCodeChange(event) {
        setAssemblyCode(event.target.value);
    }
    return(
        <div className="code-editor">
            <h4>Assembly Code</h4>
            <textarea className="assembly-input" value={sampleCode} rows={10} onChange={handleAssemblyCodeChange}></textarea>
        </div>
    );
}