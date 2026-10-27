"""Pure slot construction and independent synthetic wire-usage accounting.

These helpers do not reserve a ticket or authorize a network operation.
"""
import hashlib
import json

from . import pge_r68_contracts as native


def slot(domain, round_number, role, ordinal, input_upper, request_sha256):
    scope = native.slot_scope(domain, round_number, role, ordinal)
    stage = ('POST_RECONCILE_TERMINAL' if domain == native.DOMAINS[1] and ordinal == 4
             else 'READ_ONLY' if ordinal >= (4 if round_number == 1 else 3)
             else 'PRE_COMMIT') if role == 'TARGET' else 'SELECT'
    request = dict(slot_scope=scope, slot_contract_sha256=native.digest(scope),
                   stage=stage, ordinal=ordinal, input_upper=input_upper,
                   output_cap=scope['output_cap'], slot_cap=scope['slot_cap'],
                   request_sha256=request_sha256)
    native.require(native.validate_slot(request, domain, round_number, role), 'SLOT_INPUT_BOUND')
    return request


def _strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def replay_usage(rows, report):
    """Recompute report totals from raw fixture responses and native slot proofs.

    This validates local synthetic records only; it cannot authenticate an issuer.
    Caller must independently bind the raw rows, stdout, WAL and owner.
    """
    totals = {'input_tokens': 0, 'output_tokens': 0, 'requests': 0,
              'tool_calls': 0, 'tool_callbacks': 0}
    seen = set()
    previous_messages = None
    previous_prompt = None
    for row in rows:
        request_raw, response_raw = row['request_raw'], row['response_raw']
        if type(request_raw) is not str or type(response_raw) is not str:
            raise ValueError('WIRE_TYPE')
        request, response = _strict(request_raw), _strict(response_raw)
        if request != row['request'] or response != row['response']:
            raise ValueError('WIRE_CONTENT_MISMATCH')
        caps = set(request) & {'max_tokens', 'max_completion_tokens'}
        if len(caps) != 1 or type(request[next(iter(caps))]) is not int or request[next(iter(caps))] != 512:
            raise ValueError('WIRE_REQUEST_CAP')
        canonical = json.dumps(response, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
        if canonical != response_raw:
            raise ValueError('RESPONSE_CANONICAL')
        if hashlib.sha256(request_raw.encode('utf-8')).hexdigest() != row['request_raw_sha256']:
            raise ValueError('REQUEST_RAW_HASH')
        usage = response['usage']
        if any(type(usage.get(k)) is not int or usage[k] < 0 for k in
               ('prompt_tokens', 'completion_tokens', 'total_tokens')):
            raise ValueError('SDK_USAGE_TYPE')
        if usage['prompt_tokens'] + usage['completion_tokens'] != usage['total_tokens']:
            raise ValueError('SDK_USAGE_ADDITION')
        proof = row['proof']
        encoded_request = json.dumps(request, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
        if hashlib.sha256(encoded_request).hexdigest() != proof['request_sha256']:
            raise ValueError('REQUEST_SEMANTIC_HASH')
        messages = request['messages']
        if type(messages) is not list:
            raise ValueError('MESSAGES_TYPE')
        if previous_messages is None:
            expected_upper = len(encoded_request)
        else:
            if messages[:len(previous_messages)] != previous_messages:
                raise ValueError('PREFIX_DRIFT')
            suffix = json.dumps(messages[len(previous_messages):], sort_keys=True, separators=(',', ':'),
                                ensure_ascii=True, allow_nan=False).encode()
            expected_upper = previous_prompt + len(suffix) + 512
        if proof['input_upper'] != expected_upper:
            raise ValueError('INPUT_UPPER_RECOMPUTE')
        if usage['prompt_tokens'] > proof['input_upper'] or usage['completion_tokens'] > proof['output_cap']:
            raise ValueError('SDK_USAGE_SLOT_BOUND')
        # The fixture response contract generates exactly 20 completion tokens.
        if usage['completion_tokens'] != 20:
            raise ValueError('SYNTHETIC_COMPLETION_MISMATCH')
        if usage['prompt_tokens'] != max(1, proof['input_upper'] - 512):
            raise ValueError('SYNTHETIC_PROMPT_MISMATCH')
        response_id = response['id']
        if type(response_id) is not str or not response_id or response_id in seen:
            raise ValueError('RESPONSE_ID')
        seen.add(response_id)
        calls = response['choices'][0]['message'].get('tool_calls', [])
        if type(calls) is not list:
            raise ValueError('TOOL_CALLS_TYPE')
        totals['input_tokens'] += usage['prompt_tokens']
        totals['output_tokens'] += usage['completion_tokens']
        totals['requests'] += 1
        totals['tool_calls'] += len(calls)
        totals['tool_callbacks'] += len(calls)
        previous_messages = messages
        previous_prompt = usage['prompt_tokens']
    if any(type(report.get(k)) is not int or report[k] != v for k, v in totals.items()):
        raise ValueError('SDK_USAGE_SUM_MISMATCH')
    return totals
