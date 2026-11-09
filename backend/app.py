from flask import Flask, request, jsonify
from unicorn import UcError

from assembler import AssemblyError, assemble_program
from simulator import run_program
from instruction_explainer import explain_trace

app = Flask(__name__)


@app.route('/simulate', methods=["POST"])
def simulate():
    data = request.get_json()
    assembly_code = data["assembly_code"]
    try:
        program = assemble_program(assembly_code)

        (
            register_states,
            stack_states,
            executed_addresses,
            instruction_numbers,
            memory_accesses,
            frame_states,
        ) = run_program(program)
    except (AssemblyError, UcError) as error:
        return jsonify(error=str(error)), 400

    executed_statements = [program.instructions[address] for address in executed_addresses[1:]]
    executed_lines = [None] + [statement.line for statement in executed_statements]
    explanations = explain_trace(
        executed_statements,
        register_states,
        stack_states,
        memory_accesses,
    )

    response = {
        'register_states': register_states,
        'stack_states': stack_states,
        'executed_addresses': executed_addresses,
        'instruction_numbers': instruction_numbers,
        'executed_lines': executed_lines,
        'explanations': explanations,
        'frame_states': frame_states,
        'memory_accesses': memory_accesses,
    }

    return jsonify(response)
