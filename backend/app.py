from flask import Flask, request, jsonify
from unicorn import UcError

from assembler import AssemblyError, assemble_program
from heap import HeapError
from simulator import run_program
from instruction_explainer import explain_trace

app = Flask(__name__)
MAX_SAFE_INTEGER = (1 << 53) - 1
# The order the data sections are shown in. .text has no visualization.
DISPLAYED_SECTIONS = ('.data', '.bss', '.rodata')


def exact_display_values(registers, stack):
    # Keep the numeric trace contract while supplying exact integers to JS.
    exact = {
        'registers': {index: str(value) for index, value in enumerate(registers) if value > MAX_SAFE_INTEGER},
        'stack': {
            cell['address']: str(cell['value']) for cell in stack
            if cell['value'] is not None and cell['value'] > MAX_SAFE_INTEGER
        },
    }
    return exact if any(exact.values()) else None


def section_layout(program):
    """Describe each data section and the labels defined inside it."""
    sections = {section.name: section for section in program.sections}
    layout = []
    for name in DISPLAYED_SECTIONS:
        section = sections.get(name)
        symbols = sorted(
            (
                {'name': label, 'address': program.symbols[label]}
                for label, owner in program.owners.items()
                if owner == name and label in program.symbols
            ),
            key=lambda symbol: symbol['address'],
        )
        layout.append({
            'name': name,
            'address': section.address if section else None,
            'size': section.size if section else 0,
            'symbols': symbols,
            # Byte ranges that hold text rather than numbers.
            'strings': [list(span) for span in section.strings] if section else [],
        })
    return layout


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
            heap_states,
            heap_allocations,
            library_calls,
            pointer_states,
            section_states,
            section_versions,
        ) = run_program(program)
    except HeapError as error:
        return jsonify(error=str(error), error_parts=error.parts), 400
    except (AssemblyError, UcError) as error:
        return jsonify(error=str(error)), 400

    executed_statements = [program.instructions[address] for address in executed_addresses[1:]]
    executed_lines = [None] + [statement.line for statement in executed_statements]
    explanations, explanation_parts = explain_trace(
        executed_statements,
        register_states,
        stack_states,
        memory_accesses,
        library_calls,
        pointer_states,
    )

    response = {
        'register_states': register_states,
        'stack_states': stack_states,
        'executed_addresses': executed_addresses,
        'instruction_numbers': instruction_numbers,
        'executed_lines': executed_lines,
        'explanations': explanations,
        'explanation_parts': explanation_parts,
        'pointer_states': pointer_states,
        'exact_values': [exact_display_values(regs, stack) for regs, stack in zip(register_states, stack_states)],
        'frame_states': frame_states,
        'memory_accesses': memory_accesses,
        'heap_states': heap_states,
        'heap_allocations': heap_allocations,
        'sections': {'layout': section_layout(program), 'versions': section_versions},
        'section_states': section_states,
    }

    return jsonify(response)
