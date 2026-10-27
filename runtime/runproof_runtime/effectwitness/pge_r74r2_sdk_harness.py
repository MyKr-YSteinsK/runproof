"""One loopback host for a pinned SDK, including a real internal response-loss hop."""
import copy
import http.client
import re
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import pge_r74r2_contracts as c
from . import pge_r68_contracts as native
from .pge_r73_sdk_harness import ready_identity
from .pge_r74r2_fault import Fault

class Harness:
    def __init__(self, ctx, ct, ledger, port, launch):
        ctx.validate(ct)
        c.require(port.domain == ct['experiment']['domain'] and ledger.ctx is ctx, 'HOST_BINDING')
        self.ctx, self.ct, self.ledger, self.port, self.launch = ctx, ct, ledger, port, launch
        self.fault = Fault(ctx.scenario, port.domain)
        self.ready = self.pid = self.pending = self.internal_pending = self.failure = None
        self.rows, self.callbacks = [], []
        self.prior = self.configuration = None
        self.internal_token = secrets.token_hex(32)
        self.server = self.thread = None

    def completion(self, body, raw):
        c.require(self.ready is not None and self.pending is None and self.failure is None, 'HOST_STATE')
        allowed = {'model','messages','tools','tool_choice','parallel_tool_calls','max_tokens',
                   'max_completion_tokens','stream','temperature','thinking'}
        c.require(type(body) is dict and set(body) <= allowed and body['model'] == 'deepseek-flash' and
                  body['stream'] is False and body['parallel_tool_calls'] is False and
                  body.get('tool_choice','auto') == 'auto', 'MODEL_REQUEST_POLICY')
        caps = set(body) & {'max_tokens','max_completion_tokens'}
        c.require(len(caps) == 1 and type(body[next(iter(caps))]) is int and body[next(iter(caps))] == 512,
                  'MODEL_OUTPUT_CAP')
        domain = self.port.domain
        tools = body['tools']
        c.require(type(tools) is list and [t['function']['name'] for t in tools] == list(native.TOOLS[domain]),
                  'DOMAIN_REGISTRY')
        for tool in tools:
            function = tool['function']; schema = function['parameters']; args = native.args_for(self.ct, function['name'])
            c.require(tool['type'] == 'function' and schema['type'] == 'object' and
                      schema['additionalProperties'] is False and set(schema['properties']) == set(schema.get('required', [])) == set(args),
                      'TOOL_SCHEMA')
            c.require(all(schema['properties'][k]['type'] == ('integer' if type(v) is int else 'string')
                          for k,v in args.items()), 'TOOL_PROPERTY_TYPE')
        messages = body['messages']
        c.require(type(messages) is list and messages[:2] == [dict(role='system',content=native.INSTRUCTIONS[domain]),
                  dict(role='user',content=native.prompt(self.ct))], 'INITIAL_PROMPT')
        configuration = {k:v for k,v in body.items() if k not in ('messages','max_tokens','max_completion_tokens')}
        c.require(self.configuration is None or configuration == self.configuration, 'CONFIG_DRIFT')
        self.configuration = copy.deepcopy(configuration)
        if self.prior is not None:
            c.require(messages[:len(self.prior)] == self.prior, 'PREFIX_DRIFT')
        calls = [z for m in messages if m.get('role') == 'assistant' for z in m.get('tool_calls', [])]
        returns = [m for m in messages if m.get('role') == 'tool']
        c.require(len(calls) == len(returns) == len(self.callbacks), 'TOOL_RETURN_COUNT')
        for call, returned, row in zip(calls, returns, self.callbacks):
            c.require(call['id'] == returned['tool_call_id'] == row['call']['call_id'] and
                      call['function']['name'] == row['call']['name'] and
                      c.strict(call['function']['arguments']) == row['call']['arguments'] and
                      type(returned['content']) is str and returned['content'].encode() == c.canonical(row['result']),
                      'TOOL_RETURN_REINJECTION')
            if row['result'].get('status') == 'UNKNOWN_OUTCOME' and not self.fault.agent_exposed:
                self.fault.expose(row['call']['call_id'], row['result'])
                self.ledger.append('FAULT', domain=domain, round=self.ct['experiment']['round'], fault=self.fault.public())
        suffix = messages if self.prior is None else messages[len(self.prior):]
        upper = len(c.canonical(body)) if not self.rows else self.rows[-1]['response']['usage']['prompt_tokens'] + len(c.canonical(suffix)) + 512
        proof = self.ledger.claim_slot(self.ct, 'TARGET', body, upper, 512)
        n = len(self.rows) + 1
        sequence = list(native.TOOLS[domain][:2] if domain == c.DOMAINS[1] else native.TOOLS[domain])
        if self.ctx.scenario == 'F':
            sequence.append('inspect_config' if domain == c.DOMAINS[0] else 'reconcile_order')
        name = sequence[n-1] if n <= len(sequence) else None
        message = dict(role='assistant', content=None if name else 'Stopped safely.')
        response_id = self.ctx.owner.run_id + '-' + str(self.ct['experiment']['round']) + '-response-' + str(n)
        if name:
            call_id = self.ctx.owner.run_id + '-' + str(self.ct['experiment']['round']) + '-call-' + str(n)
            call = dict(call_id=call_id, name=name, arguments=native.args_for(self.ct, name))
            self.pending = dict(response_id=response_id, **call)
            message['tool_calls'] = [dict(id=call_id, type='function',
                function=dict(name=name, arguments=c.canonical(call['arguments']).decode()))]
        prompt_tokens = max(1, upper - 512)
        response = dict(id=response_id, object='chat.completion', created=0, model='deepseek-flash',
            choices=[dict(index=0, finish_reason='tool_calls' if name else 'stop', message=message)],
            usage=dict(prompt_tokens=prompt_tokens, completion_tokens=20, total_tokens=prompt_tokens+20))
        self.ledger.complete_slot(self.ct, 'TARGET', proof, response, response['usage'])
        self.rows.append(dict(request=body, request_raw=raw.decode('utf-8'), request_raw_sha256=c.sha(raw),
                              proof=proof, response=response, response_raw=c.canonical(response).decode('ascii')))
        self.prior = copy.deepcopy(messages)
        return response

    def callback(self, value, raw):
        c.require(self.pending is not None and self.failure is None, 'CALLBACK_STATE')
        expected = {k:self.pending[k] for k in ('call_id','name','arguments')}
        c.require(value == expected and value['call_id'] not in [r['call']['call_id'] for r in self.callbacks],
                  'CALLBACK_LINEAGE')
        token = secrets.token_hex(16)
        self.internal_pending = (token, self.pending)
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=60)
        try:
            connection.request('POST','/internal',body=c.canonical({'nonce':token}),headers={
                'Content-Type':'application/json','Authorization':'Bearer '+self.internal_token,'Connection':'close'})
            response = connection.getresponse()
            raw_result = response.read(262145)
            c.require(response.status == 200 and len(raw_result) <= 262144, 'INTERNAL_RESPONSE')
            result = c.strict(raw_result)
        except (ConnectionError, OSError, http.client.HTTPException) as exc:
            self.fault.observe(value['call_id'], type(exc).__name__)
            self.port.mark_unknown()
            result = dict(status='UNKNOWN_OUTCOME', reason='VERIFIED_INTERNAL_HTTP_RESPONSE_SUPPRESSED',
                          write_policy='STOP_WRITES_READ_ONLY_RECONCILE')
        finally:
            connection.close()
            self.internal_pending = None
        row = dict(call=self.pending, callback_raw=raw.decode('utf-8'), callback_raw_sha256=c.sha(raw),
                   result=result, result_raw=c.canonical(result).decode('ascii'),
                   result_raw_sha256=c.sha(c.canonical(result)))
        self.callbacks.append(row); self.pending = None
        self.ledger.append('TOOL_RETURN', domain=self.port.domain, round=self.ct['experiment']['round'],
                           cold=False, row=dict(**row['call'],result=result,result_sha256=c.digest(result)))
        return result

    def start(self):
        host = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                try:
                    self.connection.settimeout(60)
                    internal = self.path == '/internal'
                    expected = host.internal_token if internal else host.launch['cfg']['token']
                    c.require(self.headers.get('Authorization') == 'Bearer '+expected and
                              self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}' and
                              self.headers.get('Origin') is None and self.headers.get('Transfer-Encoding') is None,
                              'HOST_AUTH')
                    size = int(self.headers.get('Content-Length','0'))
                    c.require(0 < size <= 262144, 'HOST_BODY')
                    raw = self.rfile.read(size); c.require(len(raw) == size, 'HOST_SHORT')
                    value = c.strict(raw)
                    if internal:
                        c.require(host.internal_pending is not None and value == {'nonce':host.internal_pending[0]}, 'INTERNAL_NONCE')
                        call = host.internal_pending[1]
                        result = host.port.invoke_real(call)
                        if host.fault.suppress(call['name'], call['call_id'], result):
                            host.ledger.append('FAULT', domain=host.port.domain, round=host.ct['experiment']['round'], fault=host.fault.public())
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            return
                    elif self.path == '/ready':
                        c.require(host.ready is None and type(host.pid) is int and value == ready_identity(host.pid), 'SDK_READY_IDENTITY')
                        host.ready = value; result = {'ready':True}
                    elif self.path == '/tool':
                        result = host.callback(value, raw)
                    else:
                        c.require(self.path == '/v1/chat/completions', 'HOST_ROUTE')
                        result = host.completion(value, raw)
                    reply = c.canonical(result)
                    self.send_response(200); self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(reply))); self.end_headers(); self.wfile.write(reply)
                except BaseException as error:
                    host.failure = type(error).__name__
                    try:
                        self.send_response(409); self.send_header('Content-Length','0'); self.end_headers()
                    except OSError:
                        pass
        self.server = ThreadingHTTPServer(('127.0.0.1', self.launch['cfg']['port']), Handler)
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':.1}, daemon=True)
        self.thread.start()

    def close(self):
        if self.server:
            self.server.shutdown(); self.server.server_close()
        if self.thread:
            self.thread.join(timeout=5)
        with socket.socket() as probe:
            probe.settimeout(.2)
            closed = probe.connect_ex(('127.0.0.1', self.launch['cfg']['port'])) != 0
        return dict(thread_gone=self.thread is None or not self.thread.is_alive(), port_closed=closed)
