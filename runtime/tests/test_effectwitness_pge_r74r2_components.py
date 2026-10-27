"""Offline native-budget adversarial cases. No process or business side effects."""
import copy
import importlib
import unittest

from runtime.runproof_runtime.effectwitness import pge_r68_contracts as c
from runtime.runproof_runtime.effectwitness.pge_r68_budget import replay
from runtime.runproof_runtime.effectwitness.pge_r74r2_slot_contract import slot


def context():
    return dict(session_id='unit-session', source_kind=c.SYNTHETIC,
                budget_version=c.BUDGET_VERSION, reachable_tokens=c.REACHABLE_TOKENS,
                global_tokens=c.GLOBAL_TOKENS, caps={k:list(v) for k,v in c.CAPS.items()})


def frames(events, ctx):
    out = []
    for index, event in enumerate(events):
        event = dict(event, session_id=ctx['session_id'], clock=index)
        frame = dict(seq=index, previous=c.digest(out[-1]) if out else None, event=event)
        frame['sha256'] = c.digest(frame)
        out.append(frame)
    return out


def baseline():
    ctx = context()
    req = slot(c.DOMAINS[0], 1, 'TARGET', 1, 1000, 'a'*64)
    events = [dict(kind='OWNER', context_sha256=c.digest(ctx)),
              dict(kind='RESERVE', resource='provider', ticket='provider-1',
                   domain=c.DOMAINS[0], round=1, role='TARGET', request=req),
              dict(kind='RESULT', ticket='provider-1', status='RECEIVED_SYNTHETIC')]
    return ctx, events


class NativeReplayControls(unittest.TestCase):
    def test_attack_inventory_and_deep_slot_binding(self):
        runner=importlib.import_module('spikes.rpf-74.rev-2.runner')
        self.assertGreaterEqual(len(runner.slot_attacks()),35)
        self.assertGreaterEqual(len(runner.slot_attacks())+len(runner.manifest_attacks())+8,100)
        req=slot(c.DOMAINS[1],2,'TARGET',1,1000,'a'*64);ticket='provider-1'
        events=[{'kind':'INTENT','request':{'parameters':{'request':copy.deepcopy(req)}}},
                {'kind':'INTENT'}, {'kind':'RESERVE','resource':'provider','role':'TARGET',
                'domain':c.DOMAINS[1],'ticket':ticket,'request':copy.deepcopy(req)},
                {'kind':'MODEL_REQUEST','ticket':ticket,'request':dict(copy.deepcopy(req),ticket=ticket)}]
        m={'wal':[{'event':x} for x in events], 'domains':[{}, {'sdk':{'rows':[{'proof':dict(copy.deepcopy(req),ticket=ticket)}]}}]}
        runner.mutate_slot_request(m,None,('input_upper',),0)
        self.assertEqual(events[0]['request']['parameters']['request']['input_upper'],0)
        self.assertEqual(events[3]['request']['input_upper'],0)
        self.assertEqual(m['domains'][1]['sdk']['rows'][0]['proof']['input_upper'],0)

    def test_positive_native_ticket_is_not_released(self):
        ctx, events = baseline()
        result = replay(frames(events, ctx), ctx)
        self.assertEqual((result['counts']['provider'], result['reserved_tokens']), (1, 10000))
        self.assertEqual(set(result['tickets']), set(result['results']))

    def test_mutated_native_contracts(self):
        cases = [
            ('ticket_name', ('ticket',), 'provider-2'),
            ('ticket_duplicate_number', ('ticket',), 'provider-0'),
            ('domain_other', ('domain',), c.DOMAINS[1]),
            ('domain_unknown', ('domain',), 'unregistered'),
            ('round_other', ('round',), 2),
            ('round_zero', ('round',), 0),
            ('role_other', ('role',), 'EXPLORER'),
            ('role_unknown', ('role',), 'SYSTEM'),
            ('ordinal_zero', ('request','ordinal'), 0),
            ('ordinal_skip', ('request','ordinal'), 2),
            ('ordinal_bool', ('request','ordinal'), True),
            ('stage_wrong', ('request','stage'), 'READ_ONLY'),
            ('stage_terminal', ('request','stage'), 'POST_RECONCILE_TERMINAL'),
            ('output_too_large', ('request','output_cap'), 512),
            ('output_negative', ('request','output_cap'), -1),
            ('output_bool', ('request','output_cap'), True),
            ('input_zero', ('request','input_upper'), 0),
            ('input_negative', ('request','input_upper'), -1),
            ('input_bool', ('request','input_upper'), True),
            ('input_over_slot', ('request','input_upper'), 10000),
            ('input_over_maximum', ('request','input_upper'), 262145),
            ('slot_cap_under', ('request','slot_cap'), 9999),
            ('slot_cap_over', ('request','slot_cap'), 10001),
            ('slot_cap_bool', ('request','slot_cap'), True),
            ('contract_hash', ('request','slot_contract_sha256'), 'b'*64),
            ('request_hash_short', ('request','request_sha256'), 'a'),
            ('request_hash_nonhex', ('request','request_sha256'), 'z'*64),
            ('request_hash_integer', ('request','request_sha256'), 17),
            ('scope_round', ('request','slot_scope','round'), 2),
            ('scope_domain', ('request','slot_scope','domain'), c.DOMAINS[1]),
            ('scope_role', ('request','slot_scope','role'), 'EXPLORER'),
            ('scope_ordinal', ('request','slot_scope','ordinal'), 2),
            ('scope_output', ('request','slot_scope','output_cap'), 512),
            ('scope_slot', ('request','slot_scope','slot_cap'), 30000),
            ('scope_version', ('request','slot_scope','version'), 'wrong'),
        ]
        for label, path, value in cases:
            with self.subTest(label=label):
                ctx, events = baseline(); target = events[1]
                for key in path[:-1]: target = target[key]
                target[path[-1]] = value
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    replay(frames(events, ctx), ctx)

    def test_lifecycle_negative_controls(self):
        for label in ('missing_ticket', 'double_result', 'unsettled_then_new', 'unknown_then_new'):
            with self.subTest(label=label):
                ctx, events = baseline()
                if label == 'missing_ticket': events[2]['ticket'] = 'provider-2'
                if label == 'double_result': events.append(copy.deepcopy(events[2]))
                if label == 'unsettled_then_new': events.pop(); events.append(dict(kind='RESERVE', resource='jvm', ticket='jvm-1'))
                if label == 'unknown_then_new': events[2]['status']='UNKNOWN'; events.append(dict(kind='RESERVE', resource='jvm', ticket='jvm-1'))
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    replay(frames(events, ctx), ctx)

    def test_native_nested_bool_requires_additional_canonical_check(self):
        ctx, events = baseline()
        altered=events[1]['request']['slot_scope']
        altered['ordinal']=True
        # Historical native equality is type-insensitive here.  The rev-2
        # verifier must compare canonical bytes as well as invoke native replay.
        self.assertTrue(c.validate_slot(events[1]['request'],c.DOMAINS[0],1,'TARGET'))
        self.assertNotEqual(c.canonical(altered),c.canonical(c.slot_scope(c.DOMAINS[0],1,'TARGET',1)))


if __name__ == '__main__':
    unittest.main()
