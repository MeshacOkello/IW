from flask import Flask, request, jsonify 
from simulator import convert_assembly_to_byte, run_byte_code

app = Flask(__name__)

@app.route('/simulate', methods=["POST"])
def simulate():
    data = request.get_json()
    assembly_code = data["assembly_code"]
    byte_code = convert_assembly_to_byte(assembly_code)
    register_states, executed_addresses, instruction_numbers = run_byte_code(byte_code)

    response = {
        'register_states': register_states,
        'executed_addresses': executed_addresses,
        'instruction_numbers': instruction_numbers,
    }

    return jsonify(response)