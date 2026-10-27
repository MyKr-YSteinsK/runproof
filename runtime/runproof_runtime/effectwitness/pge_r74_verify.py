"""Offline checks of a task-owned raw manifest, its WAL and business evidence."""
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from . import pge_r74_contracts as c
from . import pge_r68_contracts as native
from .pge_r68_budget import replay
from .pge_r74_owner_source import source_identity
from .pge_r73_launch_contract import env_summary
from .pge_r73_sdk_harness import ready_identity
from .pge_r73_contracts import PIN
from .config_live_runtime import _api_response, _valid_item
from .config_live_verify import _history
from .effect_oracle import evaluate_order_effect

def _scope(path):
    path = Path(path).absolute()
    c.require(path.is_relative_to(c.WORK) and not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)),
              'VERIFY_SCOPE')
    c.require(path.resolve().is_relative_to(c.WORK.resolve()), 'VERIFY_RESOLVED_SCOPE')
    return path

def verify(path, anchor):
    path = _scope(path)
    raw = path.read_bytes()
    c.require(type(anchor) is str and re.fullmatch('[0-9a-f]{64}', anchor) and c.sha(raw) == anchor, 'RAW_ANCHOR')
    m = c.strict(raw)
    c.require(c.canonical(m) == raw and m['schema'] == 'rpf74-local-integration-manifest-v1' and
              m['owner'] == c.OWNER and m['abi'] == c.ABI and m['source_kind'] == c.SOURCE_KIND and
              m['scenario'] in c.SCENARIOS and m['model_source'] == 'SCRIPTED_PROVIDER' and
              m['provider_calls'] == 0 and m['child_attestation'] is False and m['issuer'] is False, 'MANIFEST_IDENTITY')
    c.require(m['source'] == source_identity() and m['source_sha256'] == c.digest(m['source']), 'SOURCE_IDENTITY')
    ctx = m['context']; c.run_id(ctx['session_id'])
    c.require(ctx['owner'] == c.OWNER and ctx['abi'] == c.ABI and ctx['source_kind'] == c.SOURCE_KIND and
              ctx['source_capsule_sha256'] == m['source_sha256'] and ctx['scenario'] == m['scenario'] and
              path.parent == c.ROOT / ctx['workspace'], 'CONTEXT_BINDING')
    wal_path = _scope(path.parent/'wal.jsonl')
    wal_raw = wal_path.read_bytes()
    c.require(wal_raw.endswith(b'\n') and c.sha(wal_raw) == m['wal_sha256'] and
              [c.strict(line) for line in wal_raw.splitlines()] == m['wal'], 'WAL_RAW_BINDING')
    state = replay(m['wal'], ctx)
    c.require(not state['unknown'] and not state['blocked'] and len(m['domains']) == 2 and
              m['policy_sha256'] == c.digest(m['policy']) and m['policy']['owner']['run_id'] == ctx['session_id'] and
              m['policy']['source'] == m['source_sha256'] and m['policy']['one_native_wal'] is True and
              m['policy']['source_kind'] == c.SOURCE_KIND and m['policy']['limits'] == native.LIMITS and
              m['policy']['caps'] == {k:list(v) for k,v in native.CAPS.items()} and
              m['policy']['provider_calls'] == 0 and m['policy']['refundable'] is False, 'POLICY_OR_SESSION')
    events = state['events']
    c.require(state['counts']['sdk'] == 2 and state['counts']['jvm'] == 1 and state['counts']['host'] == 2 and
              state['counts']['sqlite_refund'] == 1 and state['counts']['config_post'] == 2 and
              state['counts']['provider'] == 0 and set(state['tickets']) == set(state['results']), 'RESOURCE_COUNTS')
    slots, seen_slots, total = [e for e in events if e['kind'] == 'MODEL_REQUEST'], {}, 0
    c.require(len(slots) <= 11, 'SLOT_COUNT')
    for event in slots:
        domain, role, number = event['domain'], event['role'], event['round']
        c.require(domain in c.DOMAINS and number == c.DOMAINS.index(domain)+1 and role in ('TARGET','EXPLORER'), 'SLOT_SCOPE')
        key = (domain,role); ordinal = seen_slots.get(key,0)+1; seen_slots[key]=ordinal
        caps = native.CAPS['EXPLORER' if role == 'EXPLORER' else domain]; proof = event['request']
        c.require(ordinal <= len(caps) and proof['ordinal'] == ordinal and proof['slot_cap'] == caps[ordinal-1] and
                  type(proof['input_upper']) is int and proof['input_upper'] > 0 and type(proof['output_cap']) is int and
                  0 < proof['output_cap'] <= 512 and proof['input_upper'] + proof['output_cap'] <= proof['slot_cap'] and
                  proof['usage_type'] == 'SYNTHETIC_VALIDATED_USAGE', 'SLOT_PROOF')
        total += proof['slot_cap']
        c.require(proof['cumulative_reserved'] == total and total <= native.REACHABLE_TOKENS <= native.GLOBAL_TOKENS,
                  'SLOT_TOTAL')
    for frame in m['wal']:
        event = frame['event']; seq = frame['seq']
        if event['kind'] in ('RESERVE','RESULT'):
            c.require(seq > 0 and seq + 1 < len(m['wal']) and
                      m['wal'][seq-1]['event'].get('audit_type') == 'RPF74_BUDGET' and
                      m['wal'][seq-1]['event'].get('status') == 'GRANTED' and
                      seq > 1 and m['wal'][seq-2]['event'].get('status') == 'CHECK' and
                      m['wal'][seq-1]['event'].get('request_sha256') == c.digest(m['wal'][seq-2]['event']['request']) and
                      m['wal'][seq-2]['event']['request']['policy_sha256'] == m['policy_sha256'] and
                      m['wal'][seq+1]['event'].get('request_sha256') == m['wal'][seq-1]['event'].get('request_sha256') and
                      m['wal'][seq+1]['event'].get('native_seq') == seq and
                      m['wal'][seq+1]['event'].get('status') == ('CONFIRMED' if event['kind'] == 'RESERVE' else 'SETTLED'),
                      'BUDGET_NATIVE_PARITY')
            request = m['wal'][seq-2]['event']['request']
            resource = event['resource'] if event['kind'] == 'RESERVE' else state['tickets'][event['ticket']]['resource']
            actual = {k:v for k,v in event.items() if k not in ('kind','clock','session_id','resource','ticket')}
            c.require(request['action'] == ('RESERVE' if event['kind'] == 'RESERVE' else 'SETTLE') and
                      request['resource'] == resource and request['ticket'] == event['ticket'] and
                      request['parameters'] == actual, 'BUDGET_NATIVE_CONTENT')
    active = None
    for event in events:
        if event.get('audit_type') == 'RPF74_AUTHORIZATION':
            status = event.get('status')
            if status == 'CHECK':
                op=event['operation']
                c.require(active is None and op['owner'] == m['policy']['owner'] and
                          op['source'] == m['source_sha256'] and op['domain'] in c.DOMAINS and
                          event['operation_sha256'] == c.digest(op), 'AUTHORIZATION_OWNER_SOURCE')
                if op['phase'] == 'business':
                    ct = ctx['rounds'][c.DOMAINS.index(op['domain'])]
                    c.require(op['tool'] in native.TOOLS[op['domain']] and
                              op['arguments'] == native.args_for(ct,op['tool']) and
                              all(type(op['arguments'][k]) is type(v) for k,v in native.args_for(ct,op['tool']).items()) and
                              type(op['response_id']) is str and bool(op['response_id']) and
                              type(op['call_id']) is str and bool(op['call_id']), 'AUTHORIZATION_BUSINESS')
                active=('CHECK',op)
            elif status == 'GRANTED':
                c.require(active is not None and active[0] == 'CHECK' and event['operation'] == active[1] and
                          event['operation_sha256'] == c.digest(active[1]), 'AUTHORIZATION_GRANT')
                active=('GRANTED',active[1])
            elif status == 'COMPLETED':
                c.require(active is not None and active[0] == 'GRANTED' and
                          event['operation_sha256'] == c.digest(active[1]), 'AUTHORIZATION_COMPLETION')
                active=None
            else:
                c.require(False, 'AUTHORIZATION_STATUS')
        elif event.get('audit_type') == 'RPF74_BUDGET' and event.get('status') == 'CHECK':
            c.require(active is not None and active[0] == 'GRANTED' and
                      event['request']['operation_sha256'] == c.digest(active[1]), 'BUDGET_AUTHORIZATION_BINDING')
    c.require(active is None, 'UNFINISHED_AUTHORIZATION')
    business_ops = [e['operation'] for e in events if e.get('audit_type') == 'RPF74_AUTHORIZATION' and
                    e.get('status') == 'GRANTED' and e['operation']['phase'] == 'business']
    expected_ops = [call for row in m['domains'] for call in row['business_calls']]
    c.require(len(business_ops) == len(expected_ops), 'AUTHORIZED_BUSINESS_COUNT')
    for op, call in zip(business_ops, expected_ops):
        c.require(all(op[k] == call[k] for k in ('response_id','call_id')) and
                  op['tool'] == call['name'] and op['arguments'] == call['arguments'], 'AUTHORIZED_BUSINESS_LINEAGE')
    for domain in c.DOMAINS:
        domain_ops = [op for op in business_ops if op['domain'] == domain]
        expected_writes = ('create_config_v1','update_config_v2') if domain == c.DOMAINS[0] else ('refund_order',)
        c.require([op['tool'] for op in domain_ops if op['tool'] in c.WRITES] == list(expected_writes),
                  'BUSINESS_WRITE_ONCE')
        unknown = [i for i,e in enumerate(events) if e['kind'] == 'TOOL_RETURN' and e.get('domain') == domain and
                   e['row']['result'].get('status') == 'UNKNOWN_OUTCOME']
        if m['scenario'] == 'N':
            c.require(not unknown, 'NORMAL_HAS_UNKNOWN')
        else:
            c.require(len(unknown) == 1 and not any(e.get('audit_type') == 'RPF74_AUTHORIZATION' and
                      e.get('status') == 'GRANTED' and e['operation']['domain'] == domain and
                      e['operation']['phase'] == 'business' and e['operation']['tool'] in c.WRITES
                      for e in events[unknown[0]+1:]), 'WRITE_AFTER_UNKNOWN')
            before = [e for e in events[:unknown[0]] if e['kind'] == 'FAULT' and e.get('domain') == domain]
            after = [e for e in events[unknown[0]+1:] if e['kind'] == 'FAULT' and e.get('domain') == domain]
            c.require(any(e['fault']['triggered'] and not e['fault']['observed'] for e in before) and
                      any(e['fault']['observed'] and e['fault']['agent_exposed'] for e in after), 'FAULT_TIMELINE')
    positions = {}
    c.require(m['domains'][0]['sdk']['pid'] != m['domains'][1]['sdk']['pid'], 'DISTINCT_CHILD_PROCESSES')
    for index, row in enumerate(m['domains'], 1):
        ct, choice, sdk, effect = row['contract'], row['choice'], row['sdk'], row['effect']
        domain = c.DOMAINS[index-1]
        c.require(ct == ctx['rounds'][index-1] and ct['experiment']['owner'] == c.OWNER and
                  ct['experiment']['domain'] == domain and choice['domain'] == domain and choice['round'] == index and
                  choice['candidate_id'] == ct['experiment']['candidate_id'] and choice['source'] == 'SCRIPTED_EXPLORER' and
                  choice['input_sha256'] == c.digest(choice['input']), 'CHOICE_SCOPE')
        if index == 2:
            c.require(choice['input']['feedback'] == m['domains'][0]['feedback'] and
                      choice['input']['feedback_sha256'] == c.digest(m['domains'][0]['feedback']), 'FEEDBACK_LINEAGE')
        c.require(sdk['factory'] == 'pge_r74_launch_factory.LaunchFactory.launch' and sdk['owner'] == c.OWNER and
                  sdk['source_sha256'] == m['source_sha256'] and type(sdk['pid']) is int and sdk['pid'] > 0 and
                  sdk['exit'] == 0 and sdk['error'] is None and all(sdk['cleanup'].values()) and
                  sdk['report']['status'] == 'COMPLETED' and sdk['report']['pid'] == sdk['pid'] and
                  sdk['ready'] == ready_identity(sdk['pid']) and sdk['model_source'] == 'SCRIPTED_PROVIDER' and
                  sdk['report']['version'] == '2.57.0' and
                  sdk['report']['openai_version'] == '3.35.1' and
                  sdk['report']['python_executable_sha256'] == PIN['python_executable_sha256'] and
                  sdk['report']['sdk_source_sha256'] == PIN['sdk_source_sha256'] and
                  sdk['report']['openai_source_sha256'] == PIN['openai_source_sha256'] and
                  sdk['report']['provider_key_present'] is False and sdk['report']['business_key_present'] is False and
                  not sdk['report']['guard_denials'] and not sdk['report']['denied_files'] and
                  sdk['report']['final_text_persisted'] is False, 'SDK_IDENTITY')
        launch = c.strict(_scope(path.parent/'runs'/ct['experiment']['run_id']/'sdk'/'launch-input.json').read_bytes())
        expected_folder = path.parent/'runs'/ct['experiment']['run_id']/'sdk'
        stdout = _scope(expected_folder/'stdout.raw').read_bytes()
        stderr = _scope(expected_folder/'stderr.raw').read_bytes()
        c.require(c.sha(stdout) == sdk['stdout_sha256'] and c.sha(stderr) == sdk['stderr_sha256'] and
                  not stderr and c.strict(stdout) == sdk['report'], 'SDK_RAW_PROCESS_REPORT')
        c.require(c.digest(launch) == sdk['request_sha256'] and launch['cfg_sha256'] == sdk['cfg_sha256'] and
                  launch['cfg']['domain'] == domain and launch['cfg']['total_token_limit'] == sum(native.CAPS[domain]) and
                  len(launch['env']) == 10 and len(sdk['env_observation']) == 1 and
                  launch['cwd'] == str(expected_folder) and launch['cfg']['write_root'] == str(expected_folder) and
                  launch['argv'][1:] == ['-I','-B','-X','utf8',str(c.ROOT/'runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py')] and
                  launch['env_summary'] == env_summary(launch['env'], expected_folder) and
                  sdk['env_observation'][0]['env_sha256'] == launch['env_summary']['sha256'], 'SDK_LAUNCH_BINDING')
        fault = sdk['fault']
        flags = [fault[k] for k in ('planned','triggered','observed','agent_exposed')]
        c.require(all(type(flag) is bool for flag in flags) and
                  flags == ([False]*4 if m['scenario']=='N' else [True]*4), 'FAULT_FOUR_STATES')
        if m['scenario'] == 'F':
            c.require(fault['channel'] == 'SAME_HOST_INTERNAL_HTTP' and fault['transport_error'] in
                      ('RemoteDisconnected','ConnectionResetError','ConnectionAbortedError'), 'FAULT_TRANSPORT')
        expected = list(native.TOOLS[domain][:2] if index == 2 else native.TOOLS[domain])
        if m['scenario'] == 'F': expected.append('inspect_config' if index == 1 else 'reconcile_order')
        callbacks = sdk['callbacks']; c.require([r['call']['name'] for r in callbacks] == expected, 'CALL_SEQUENCE')
        business = row['business_calls']
        c.require(len(business) == len(callbacks), 'BUSINESS_CALLBACK_COUNT')
        c.require(sdk['report']['requests'] == len(sdk['rows']) == len(callbacks)+1 and
                  sdk['report']['tool_calls'] == sdk['report']['tool_callbacks'] == len(callbacks), 'SDK_COUNTS')
        c.require(len({r['call']['call_id'] for r in callbacks}) == len(callbacks), 'CALL_ID_REPLAY')
        for i, call in enumerate(callbacks):
            actual = business[i]
            c.require(all(actual[k] == call['call'][k] for k in ('response_id','call_id','name','arguments')) and
                      actual['result_sha256'] == c.digest(actual['result']), 'BUSINESS_CALL_LINEAGE')
            c.require(call['call']['arguments'] == native.args_for(ct, call['call']['name']) and
                      c.strict(call['callback_raw']) == {k:call['call'][k] for k in ('call_id','name','arguments')} and
                      c.sha(call['callback_raw'].encode()) == call['callback_raw_sha256'] and
                      call['result_raw'].encode() == c.canonical(call['result']) and
                      call['result_raw_sha256'] == c.sha(call['result_raw'].encode()), 'CALLBACK_CONTENT')
            next_messages = sdk['rows'][i+1]['request']['messages']
            returned = [z for z in next_messages if z.get('role') == 'tool' and z.get('tool_call_id') == call['call']['call_id']]
            c.require(len(returned) == 1 and returned[0]['content'].encode() == c.canonical(call['result']), 'SDK_REINJECTION')
        for row_request in sdk['rows']:
            c.require(c.strict(row_request['request_raw']) == row_request['request'] and
                      c.sha(row_request['request_raw'].encode()) == row_request['request_raw_sha256'] and
                      row_request['response_raw'].encode() == c.canonical(row_request['response']) and
                      row_request['proof']['request_sha256'] == c.digest(row_request['request']) and
                      row_request['proof']['input_upper'] >= len(c.canonical(row_request['request'])), 'SDK_WIRE_BYTES')
        actual_target_slots = [e['request'] for e in events if e['kind'] == 'MODEL_REQUEST' and
                               e.get('domain') == domain and e.get('role') == 'TARGET']
        c.require(actual_target_slots == [r['proof'] for r in sdk['rows']], 'SDK_WAL_SLOT_BINDING')
        explorer_slots = [e['request'] for e in events if e['kind'] == 'MODEL_REQUEST' and
                          e.get('domain') == domain and e.get('role') == 'EXPLORER']
        c.require(explorer_slots == [choice['proof']] and choice['proof']['request_sha256'] == c.digest(choice['input']),
                  'EXPLORER_WAL_SLOT_BINDING')
        if m['scenario'] == 'F':
            unknown = [r for r in callbacks if r['result'].get('status') == 'UNKNOWN_OUTCOME']
            c.require(len(unknown) == 1 and unknown[0]['call']['call_id'] == fault['call_id'], 'FAULT_CALL_LINEAGE')
            committed = [r for r in business if r['call_id'] == fault['call_id']]
            c.require(len(committed) == 1 and committed[0]['result'].get('status') == 'COMMITTED' and
                      committed[0]['result_sha256'] == fault['committed_sha256'], 'FAULT_COMMIT_BEFORE_DROP')
        if index == 1:
            effect_contract = ct['effect']
            before = effect['before']; after = effect['after']
            c.require(_api_response(before[0],404,4041,'none')[0] and _api_response(before[1],200,0,'list') == (True, []),
                      'CONFIG_BEFORE')
            ok, item = _api_response(after[0],200,0,'item'); okh, history = _api_response(after[1],200,0,'list')
            okl, listed = _api_response(after[2],200,0,'list')
            c.require(ok and _valid_item(item,effect_contract,2,'rpf53-v2') and okh and _history(history,effect_contract)
                      and okl and len(listed) == 1 and _valid_item(listed[0],effect_contract,2,'rpf53-v2') and
                      effect['backend'] == 'REAL_JAVA_H2_HTTP' and
                      effect['environment']['jar_sha256'] == native.SOURCE_JAR_SHA256 and
                      effect['environment']['jar_bytes'] == native.SOURCE_JAR_BYTES and
                      effect['environment']['command_verified'] and effect['environment']['listener_owned'],
                      'CONFIG_AFTER')
        else:
            oracle = evaluate_order_effect(ct['effect'],ct['experiment']['environment_id'],
                                           effect['before']['data'],effect['after']['data'])
            c.require(oracle['contract_outcome'] == 'CONTRACT_SATISFIED_IN_RUN' and
                      len(effect['after']['data']['receipts']) == 1, 'ORDER_AUTHORITY')
            database = _scope(path.parent/'runs'/ct['experiment']['run_id']/'business'/'orders.sqlite3')
            c.require(c.sha(database.read_bytes()) == effect['database_sha256'], 'ORDER_DATABASE_RAW')
            with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON'); db.execute('BEGIN')
                observed = dict(environment=dict(db.execute('SELECT * FROM environment').fetchone()),
                                order=dict(db.execute('SELECT * FROM orders WHERE order_id=?',
                                          (ct['effect']['order_id'],)).fetchone()),
                                receipts=[dict(x) for x in db.execute('SELECT * FROM refunds ORDER BY operation_id')])
                db.commit()
            expected = effect['after']['data']
            c.require(effect['backend'] == 'REAL_LOCAL_SQLITE' and
                      effect['before']['sha256'] == c.digest(effect['before']['data']) and
                      effect['after']['sha256'] == c.digest(expected) and
                      all(observed[k] == expected[k] for k in observed), 'ORDER_DATABASE_AUTHORITY')
        c.require(all(row['cleanup'].values()) and row['feedback']['source_effect_sha256'] == c.digest(effect) and
                  row['feedback']['source_contract_sha256'] == c.digest(ct), 'DOMAIN_EVIDENCE')
        for kind in ('CHOICE','DOMAIN_VERIFIED','FEEDBACK_FROZEN'):
            matches = [i for i,e in enumerate(events) if e['kind'] == kind and e.get('round') == index]
            c.require(len(matches) == 1, 'EVENT_CARDINALITY')
            positions[index,kind] = matches[0]
        c.require(positions[index,'CHOICE'] < positions[index,'DOMAIN_VERIFIED'] < positions[index,'FEEDBACK_FROZEN'],
                  'FEEDBACK_ORDER')
        c.require(events[positions[index,'CHOICE']]['choice'] == choice and
                  events[positions[index,'CHOICE']]['choice_sha256'] == c.digest(choice) and
                  events[positions[index,'DOMAIN_VERIFIED']]['effect_sha256'] == c.digest(effect) and
                  events[positions[index,'DOMAIN_VERIFIED']]['sdk_receipt_sha256'] == c.digest(sdk) and
                  row['feedback']['verified_seq'] == positions[index,'DOMAIN_VERIFIED'] and
                  events[positions[index,'FEEDBACK_FROZEN']]['feedback'] == row['feedback'] and
                  events[positions[index,'FEEDBACK_FROZEN']]['feedback_sha256'] == c.digest(row['feedback']),
                  'EVENT_CONTENT_BINDING')
    c.require(positions[1,'FEEDBACK_FROZEN'] < positions[2,'CHOICE'], 'CROSS_DOMAIN_ORDER')
    return dict(status='PASS', scenario=m['scenario'], manifest_sha256=c.sha(raw), source_sha256=m['source_sha256'],
                wal_sha256=m['wal_sha256'], run_id=ctx['session_id'], domain_count=2, issuer=False)
