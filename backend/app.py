import logging

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from unicorn import UcError

import errors
from assembler import AssemblyError
from assembly_worker import AssemblyTimeout, assemble_in_worker, timeout_error
from heap import HeapError
from library_io import InputProtocolError
from simulator import run_program
from instruction_explainer import explain_trace
from register_writes import register_writes

app = Flask(__name__)
logger = logging.getLogger(__name__)
MAX_SAFE_INTEGER = (1 << 53) - 1
MAX_SOURCE_BYTES = 1 << 20
MAX_INPUT_EVENTS = 10_000
EXECUTION_LIMIT = 10_000
# The order the data sections are shown in. .text has no visualization.
DISPLAYED_SECTIONS = ('.data', '.bss', '.rodata')


def error_response(error, code):
    """One JSON shape for every failure, with the flat fields kept for clients
    that only read `error` and `error_parts`."""
    body = {
        'error': errors.legacy_text(error),
        'error_parts': errors.legacy_parts(error),
        'error_info': error,
        'status': {'state': 'error', 'kind': error['kind']},
    }
    if error.get('line') is not None:
        body['status']['line'] = error['line']
    return jsonify(body), code


def bad_request(message, *, suggestion=None):
    return error_response(
        errors.payload(errors.REQUEST, message, suggestion=suggestion), 400)


@app.errorhandler(HTTPException)
def handle_http_error(error):
    """Answer a bad route, method or body with JSON, never an HTML page.

    The frontend parses every response as JSON, so an HTML error page would
    surface to the student as a parser error instead of the real problem.
    """
    messages = {
        400: 'The request body was not valid JSON.',
        404: 'There is no such endpoint on the simulator backend.',
        405: 'That HTTP method is not allowed on this endpoint.',
        413: 'The request body is too large.',
        415: 'The request must be sent as JSON with Content-Type: application/json.',
    }
    message = messages.get(error.code) or error.description or 'The request could not be handled.'
    payload = errors.payload(errors.REQUEST, message, detail=f'HTTP {error.code}')
    return error_response(payload, error.code or 400)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    """A bug in the simulator: log it in full, show the student a plain note.

    The traceback stays on the server. The response says the program was not
    at fault, so an internal failure is never reported as a student mistake.
    """
    logger.exception('Unhandled error while simulating: %s', error)
    return error_response(errors.payload(
        errors.INTERNAL, errors.INTERNAL_MESSAGE,
        detail=type(error).__name__,
    ), 500)


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


def parse_body():
    """Decode the request body, or say precisely how it was unreadable."""
    if not request.is_json:
        return None, 'The request must be sent as JSON with Content-Type: application/json.'
    try:
        data = request.get_json()
    except HTTPException:
        return None, 'The request body is not valid JSON.'
    if not isinstance(data, dict):
        return None, 'The request body must be a JSON object.'
    return data, None


def validate(data):
    """Check the fields before any work. Returns a message, or None if valid."""
    source = data.get('assembly_code')
    if not isinstance(source, str):
        return 'assembly_code must be a string', 'Send the editor contents as assembly_code.'
    if len(source.encode('utf-8', errors='replace')) > MAX_SOURCE_BYTES:
        return f'assembly_code must be at most {MAX_SOURCE_BYTES} bytes', None

    events = data.get('input_events', [])
    if (not isinstance(events, list) or len(events) > MAX_INPUT_EVENTS
            or any(not isinstance(event, dict) for event in events)):
        return 'input_events must be a list of input submissions', None

    limit = data.get('execution_limit', EXECUTION_LIMIT)
    if type(limit) is not int or not 1 <= limit <= EXECUTION_LIMIT:
        return f'execution_limit must be an integer from 1 to {EXECUTION_LIMIT}', None
    return None, None


def safe_explanations(*arguments, **options):
    """Explanations are commentary: a bug in one must not discard the trace."""
    try:
        return explain_trace(*arguments, **options)
    except Exception:
        logger.exception('Explanation failed; serving the trace without explanations')
        steps = len(arguments[1])
        return [None] * steps, [None] * steps


@app.route('/simulate', methods=["POST"])
def simulate():
    data, unreadable = parse_body()
    if unreadable is not None:
        return bad_request(unreadable)
    message, suggestion = validate(data)
    if message is not None:
        return bad_request(message, suggestion=suggestion)

    assembly_code = data['assembly_code']
    input_events = data.get('input_events', [])
    execution_limit = data.get('execution_limit', EXECUTION_LIMIT)

    try:
        # In a worker process: Keystone can hang on malformed source in native
        # code, and a hang there must not take this backend with it.
        program = assemble_in_worker(assembly_code)
    except AssemblyError as error:
        return error_response(errors.assembly_error(
            error.message, line=error.line, source=assembly_code,
            suggestion=error.suggestion, detail=error.detail,
            kind=error.kind or errors.ASSEMBLY,
        ), 400)
    except AssemblyTimeout:
        return error_response(timeout_error(), 400)

    try:
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
            stdout_states,
            stdout,
            status,
            transfers,
        ) = run_program(program, input_events, execution_limit)
    except InputProtocolError as error:
        # The submitted input does not match the run being continued, so the
        # trace cannot be rebuilt: this is a request problem, not a program bug.
        return error_response(errors.payload(
            errors.REQUEST, str(error),
            suggestion='Load the program again to start a fresh run.',
        ), 400)
    except HeapError as error:
        message = errors.render(error.parts)
        return error_response(errors.runtime_error(
            message, parts=error.parts, kind=error.kind,
            suggestion=errors.heap_suggestion(message),
        ), 400)
    except UcError as error:
        text, parts, suggestion, detail = errors.describe_unicorn_error(error, None, ())
        return error_response(errors.runtime_error(
            text, parts=parts, suggestion=suggestion, detail=detail), 400)

    executed_statements = [program.instructions[address] for address in executed_addresses[1:]]
    executed_lines = [None] + [statement.line for statement in executed_statements]
    explanations, explanation_parts = safe_explanations(
        executed_statements,
        register_states,
        stack_states,
        memory_accesses,
        library_calls,
        pointer_states,
        status.get('returned'),
        transfers=transfers,
        exited=status.get('exited'),
    )

    response = {
        'register_states': register_states,
        'register_writes': register_writes(executed_statements, register_states, library_calls),
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
        'stdout_states': stdout_states,
        'stdout': stdout,
        'status': status,
        'run_settings': {'execution_limit': execution_limit},
    }

    if status['state'] == 'error':
        # The steps recorded before the fault are still in the response, so the
        # student can step through them and see the state that caused it.
        error = status.get('error_info')
        if error is not None:
            error = dict(error, source_line=errors.source_line_text(assembly_code, error.get('line')))
            status['error_info'] = {key: value for key, value in error.items() if value is not None}
            status['kind'] = error['kind']
        response.update(error=status['error'], error_parts=status.get('error_parts'),
                        error_info=status.get('error_info'))
    return jsonify(response), 400 if status['state'] == 'error' else 200
