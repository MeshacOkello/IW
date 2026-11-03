from flask import Flask, request, jsonify
from simulator import (
    convert_assembly_to_byte,
    run_byte_code,
    map_addresses_to_lines,
)
from instruction_explainer import explain_trace

app = Flask(__name__)


@app.route('/simulate', methods=["POST"])
def simulate():
    data = request.get_json()
    assembly_code = data["assembly_code"]
    byte_code = convert_assembly_to_byte(assembly_code)

    address_to_line, address_to_labels = map_addresses_to_lines(assembly_code)

    (
        register_states,
    stack_states,
    executed_addresses,
    instruction_numbers,
    memory_accesses,
    frame_states,
    ) = run_byte_code(byte_code, address_to_labels)

    executed_lines = [
        address_to_line.get(address)
        for address in executed_addresses
    ]

    # Check that the source mapping matches the assembled code length.
    lines_match = len(address_to_line) * 4 == len(byte_code)

    explanations = explain_trace(
        assembly_code.splitlines(),
        executed_lines,
        register_states,
        stack_states,
        memory_accesses,
        lines_match,
    )

    response = {
        'register_states': register_states,
        'stack_states': stack_states,
        'executed_addresses': executed_addresses,
        'instruction_numbers': instruction_numbers,
        'executed_lines': executed_lines,
        'explanations': explanations,
        'frame_states': frame_states,
    }

    return jsonify(response)
