"""RPF88: unchanged R72 unittest cohort, fresh test-only physical owner.

No formal coverage promotion. CPython interfaces plus explicit SQLite admission,
not a kernel sandbox, independent issuer, or real Provider/SDK experiment.
"""
from __future__ import annotations
import argparse
import ast
import builtins
from collections import Counter
from contextlib import closing
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import subprocess
import sys
import sysconfig
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, unquote, parse_qsl

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
BASE = 'ed242f02cc3e40ac0a9f084619d4335a028bfbc6'
MODULE = 'runtime.tests.test_effectwitness_pge_r72'
TARGET = 'runtime/tests/test_effectwitness_pge_r72.py'
NAMES = ('test_immutable_policy_strict_identity', 'test_native_direct_reserve_denied_before_wal_write',
 'test_native_direct_settle_and_append_denied', 'test_no_operation_no_sqlite_setup',
 'test_session_reserve_settle_native_parity', 'test_duplicate_settlement_is_not_reclaimed',
 'test_resource_limit_session_once', 'test_unknown_refund_stops_new_writes',
 'test_unsettled_refund_stops_second_write', 'test_crash_check_before_reserve',
 'test_crash_native_reserve_before_confirmation', 'test_valid_owner_missing_policy_does_not_enter_port',
 'test_wrong_policy_does_not_enter_port', 'test_component_eleven_slots_permanent_native_caps',
 'test_component_rejects_slot_and_price_forgery', 'test_real_sqlite_normal_gate_and_policy',
 'test_real_sqlite_unknown_readonly_gate_and_policy', 'test_boolean_round_and_unknown_parameter_rejected')
EXCLUDED = ('test_parent_child_policy_two_domain_totals', 'test_actual_cfg_limit_threshold_and_legacy35000',
 'test_parent_child_noncanonical_bool_and_crossdomain', 'test_config_fields_domain_pin_and_output_limits',
 'test_parent_contract_rejects_changed_policy', 'test_source_drift_independent_capsule', 'test_junction_and_torn_receipt')
IDS = [MODULE+'.BudgetTests.'+n for n in NAMES]
PINS = {'spikes/rpf-53/rev-6/config-live-evidence.json': {'blob': 'b80c7d1b98daf9d336e8c90caa767b3d1113a3e9', 'lf': 'f5e46947ae2a2583db51727e85c4f9e3d6c9d6499a1b24833dfffe1799438b43'}, 'spikes/rpf-68/rev-3/probe.py': {'blob': '2758370aeeb012840807930c69c5b865e6713ae1', 'lf': '2f62f4b61066f92d7d48a00fefa584273c177656c10afff686b90a001eddb10a'}, 'runtime/runproof_runtime/effectwitness/pge_r68_budget.py': {'blob': 'ef34deac1efb3b828e779359f8c65e511b014939', 'lf': '86a9cec7bf426c83aa0e98d85ca981b69e40c644efb6640999fa9e5141f7b5cc'}, 'runtime/runproof_runtime/effectwitness/pge_r68_driver.py': {'blob': '3896c73991957b0d0e70f83e77cece8318b21c3b', 'lf': 'ae98e1db1a194b3b72c0d469b31545726babfaea2ff4ca6eaa20c4d67b018750'}, 'runtime/runproof_runtime/effectwitness/pge_r68_session.py': {'blob': 'f613345128b2040a06879b625a7733c72bd7c1c0', 'lf': 'bd5ab2c74e14c7b6573d062522db09865c9b54fecb8e303205781ff75aad25af'}, 'runtime/runproof_runtime/effectwitness/pge_r68_verify.py': {'blob': '48baa89ec24a51ebe39a597e89aa1753e0a200db', 'lf': '3e4b89e5a0142887b42640c56db7775001684bc3f96b26f120fa28cdd8122d78'}, 'runtime/runproof_runtime/effectwitness/contracts.py': {'blob': '0321f5d7353f7aa09f00df55806f0815381ac4dc', 'lf': 'dad9f0f56d0533b28b6f02ae9a6b9dfad1cbc3f53bf70825b6f0c54ffdbf6d4d'}, 'runtime/runproof_runtime/models.py': {'blob': '05343951e4a2faf34c80e2657586296ca3f36897', 'lf': 'f5b9a2e1dc17ed8f923f721c52401f44ae814726e70cc5434596f7b9c1bc55b3'}, 'runtime/runproof_runtime/effectwitness/config_live_verify.py': {'blob': '88156284be44671f823cc511d44d36028511dbba', 'lf': '75fa9329f8773279801b6e5c3165fe0bd8fc22ead60f7001f6c885827f8d0282'}, 'runtime/runproof_runtime/effectwitness/config_live_contracts.py': {'blob': '08f78670f110d7a41035494ce37e3b1436bb5787', 'lf': '4a2e111c643d20e2873f4b46c665c58bce3b2b4fa27f5e55fe6467a00ee5443f'}, 'runtime/runproof_runtime/effectwitness/config_live_runtime.py': {'blob': 'ff16b23d13ffa82cc2571b1f6b64e92f8f380e7e', 'lf': 'b973698450a42be8f74838f5aa8377bb45010694a2aa555819caa48ceb1c86a9'}, 'runtime/runproof_runtime/effectwitness/effect_oracle.py': {'blob': '3d1322472b1621f4061db4331914dc4e36b23fa0', 'lf': '066f789e9b0044378ef896bd065df7b788ef27398163bac4acb63e898bd9c73c'}, 'runtime/runproof_runtime/effectwitness/pge_r68_explorer.py': {'blob': 'b775a9d1fcebaaf5984d3a9499aca153fec00e9e', 'lf': '3812392af66340099f44ee4efe1dbf80856346ce53eb317ae39f822858c98235'}, 'runtime/runproof_runtime/effectwitness/pge_r68_context.py': {'blob': 'cb69d8bb696f03224fdffde55999a8f44274802c', 'lf': '3daa88f37a8b3f3e0d7041e397443fa40997594efca3d52dc25dfd1e76aff4c9'}, 'runtime/runproof_runtime/effectwitness/pge_r68_contracts.py': {'blob': '8c59dd7b12a5fc0e7d7f80e6f72810085282ebe3', 'lf': 'ef2bbc53af1650613926c37dbe204cea21331c6ed7415c92058626020b503a23'}, 'runtime/runproof_runtime/effectwitness/config_experiment_verify.py': {'blob': 'e675dd04d6a9bcc09c87d798222d48f972488f3f', 'lf': '41fc05e3da0b3b89da5cad0a63fa8f0f7017d7d63cddfb8aabf8fd24343f5db3'}, 'runtime/runproof_runtime/effectwitness/config_experiment_contracts.py': {'blob': '8d2c05bd874a8517ccfdc6ba20fbf589e8130d7f', 'lf': '1866cbe105ef387793f6132c5801c86ae7c07189e64baeaf5ae21991851eb631'}, 'runtime/runproof_runtime/effectwitness/pge_r68_config_port.py': {'blob': '34d5fd69480359cb09d8c839596dbfd3d5aabcd7', 'lf': '3fc3e12bbef251f853527cb2b16a23a819babda96997af9056344db9ae672612'}, 'runtime/runproof_runtime/effectwitness/pge_r68_order_port.py': {'blob': 'e3990d1c5f887592cbeff2a10db7a7b27292115f', 'lf': '4fabc4aa26cf54cb6b387f06c895123432fb9ce0fc3a05c89d01c7401884babb'}, 'runtime/runproof_runtime/effectwitness/orders.py': {'blob': 'f302fe8a3dd71ae08121d427407c427757666942', 'lf': 'b28a00b9b43342ac6d85693aee0a5902aa60d4060446347a6f381a7de4b6d3ef'}, 'spikes/rpf-72/probe.py': {'blob': '9c733e541f2e70d2d4c0205cffa124af71467171', 'lf': '10df49b4a17e545ee281b271ed6220c6b8193cd025757922a591a5ceaed8b819'}, 'runtime/runproof_runtime/effectwitness/pge_r72_sdk_contract.py': {'blob': '029c4f83c543b0666b30a3918add84df027256e2', 'lf': '9051b6e92aeb57de388e7480aafeaab44f86a3930e947bc2d5d1d089304348fb'}, 'runtime/runproof_runtime/effectwitness/pge_r72_budget_policy.py': {'blob': '7cb8e5dbdc734a983c0c366f6c7ccab3d479e3c1', 'lf': '70243f5eae873e929523486fb6f247419c723d05b906e4b0fe24702284cde27e'}, 'runtime/runproof_runtime/effectwitness/pge_r72_contracts.py': {'blob': 'efea283ef6288a4cb0452ec9fbdd15340bacf46f', 'lf': 'be91b7d536530e134d3805c4f133d91574405eddc23e29832e9970a26d4422b1'}, 'spikes/rpf-71/probe.py': {'blob': '127ce2df3c9e0b8ccd2cb3816c62615da4732699', 'lf': 'fd3efaac12b75fd8bad3fc5f4538408cb1a93e4a0df121d312bd662bc14fb261'}, 'spikes/rpf-70/probe.py': {'blob': '90ec3173e7d5724af2e81b33f94de2e266b66ec4', 'lf': 'c5f9af2f76e1115540ab6f99b72f4842b6e4d4629cd0dd5c2eec0109a20efee0'}, 'runtime/runproof_runtime/effectwitness/pge_r70_ports.py': {'blob': 'dfb63bc7407cf9b8e00d46d47138652bc3029f95', 'lf': '99d054bee0ec93e4ebf7863bd25644b382b3e79b5664b2c00ba556737d881e7d'}, 'runtime/runproof_runtime/effectwitness/pge_r70_capability.py': {'blob': '3edfd818e900083874c05987b17aff8cca06d649', 'lf': '99ab82737e56c3b7c7348abad67a303f02a05d705e64200dad3946bf87868ef5'}, 'runtime/runproof_runtime/effectwitness/pge_r70_owner_source.py': {'blob': '878f95ea6e18c823d9b956326ff39bd35c62d6f7', 'lf': 'd3e8daf092cd7b20305b78833553f5c3a84e55a1c9efe7f8f36facf416a10846'}, 'runtime/runproof_runtime/effectwitness/pge_r70_contracts.py': {'blob': 'a4232f929b145b6a4e9170302a02f5e8b9312888', 'lf': 'a652266689efb30b597c9532b79bf31f855dd37595d27f341e4f3c0e547a6061'}, 'spikes/rpf-55/probe.py': {'blob': '6a1ae9d154adcc35f69455b32982faaedb5483bc', 'lf': 'a5c9745409531cb71632c236ce5e3a09c86b0d3c776ca35ebdf76eed9dc77f5c'}, 'runtime/runproof_runtime/effectwitness/config_experiment_adapter.py': {'blob': '257b677a91da15032962dc3eaac8729dd01e66a0', 'lf': '3c88e456b4503bb5e8fbe2b87cef5a80381872be4976d43e9848cb7670a78e43'}, 'spikes/rpf-53/probe.py': {'blob': 'b15c595754c1ff4b213d3cbc0c6324622b9083e7', 'lf': 'b877325e833c6170148e73fd2b290ab0a4165033668570744067cee24ef2210e'}, 'runtime/tests/test_effectwitness_pge_r71.py': {'blob': '0d4e5342a1e0cb6a0d2d890181d70e20ec658162', 'lf': 'd11733f56ea35d5db606a5ac2a9d39bbb648ac1ebd5b54cbff5fe84d53ae87d2'}, 'runtime/runproof_runtime/effectwitness/pge_r71_ports.py': {'blob': 'fa61b3c66dcfa2cf529a740f361432830ea3f247', 'lf': '6158c301a050a6dbee14dcc1ba7d639f3b77a5e623b55d63f2311c27520a06c3'}, 'runtime/runproof_runtime/effectwitness/pge_r71_budget_ledger.py': {'blob': '45d5cc1c77f08a95998aef8091610121356fc58e', 'lf': '02c2eb2835b546073904d03e8db10fbdc7cf3f21d206b8c4fbc1c73ca68ac746'}, 'runtime/runproof_runtime/effectwitness/pge_r71_budget_policy.py': {'blob': 'f3b957ba9d520a239db0ddf58b5cf85ef372e586', 'lf': 'bf183b085f659e937494a36ab0c0ff2c42ce66c8d76d6914a64fe05f1e03a597'}, 'runtime/runproof_runtime/effectwitness/pge_r71_contracts.py': {'blob': '3aa0bc586c23b18034921b175fad8c8bce7cf6d1', 'lf': '43c40f8b63eb0cf6f8e9f478f87e0350a0fcbdb467256d7ee92815a5c9e60417'}, 'runtime/runproof_runtime/effectwitness/pge_r71_owner_source.py': {'blob': '121ce3d8a9fdbb11dc37229a86469f1f4db152df', 'lf': '1164324fb618f975d7fcbe3cd16a28ae08829aa7c9ce349972514b3f3c9cf930'}, 'runtime/runproof_runtime/effectwitness/pge_r71_capability.py': {'blob': '012cd10318d0253a5b8b1ac00a8adfcd1aae6845', 'lf': 'd1fac0452e40f24a3d10445fa7b150d9c035f7977c66dd5df6c451c96ce0f19b'}, 'runtime/tests/test_effectwitness_pge_r70.py': {'blob': '70bb2ab41b88e0f117af3d8010a5cccf370a57fb', 'lf': 'e346e1a357b859e68a221dd1dc6a03e321e77eb4d08b8be981eaefe1db6d0919'}, 'runtime/runproof_runtime/effectwitness/pge_r70_verify.py': {'blob': '8e0cc897dabdbc3812059a545454ad5204b8ea42', 'lf': '2c650c99231193edaad9484f08c4c55264f996bca7a11c8197b31b7856de69d3'}, 'runtime/tests/test_effectwitness_pge_r68.py': {'blob': '654dd0c9e87a39287a66c48958d52cf8b9398234', 'lf': 'a5cc81986279dbbbdb6a419d1dd1c94e00eeb6d6d6ce4959e37a66b6077a4449'}, 'runtime/runproof_runtime/effectwitness/pge_r67_order_child.py': {'blob': 'eca1b240f9512b665792141e53c4103c5b4dcddb', 'lf': '1c3a3543061d81c5a07654284cfa531160498facbb0bb57175bf2fe94c3ee90c'}, 'runtime/runproof_runtime/effectwitness/pge_r66_sdk_child_v5.py': {'blob': 'b10e9bbc7d59fcab7b0dea6db9c214a27b0dce01', 'lf': 'a27f4970754bf1de38338f935a2056d91c98412d63ef7ee37d6c2cce00ee9504'}, 'runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py': {'blob': '632224882fef588bbc26ce78a6bb5daaf9873f53', 'lf': 'c278eae783e3fa3eacdb0c852c9ab7b4a9685bb7f4669395bb316460cd5eb5f7'}, 'runtime/runproof_runtime/effectwitness/pge_r70_migration.py': {'blob': 'a92597af93bc2a3d42fc0574032ff24eae9bbe34', 'lf': '662413e152268a130e9c7b7ae1b265960a7d2b53a544044d1da127813ed30b8d'}, 'runtime/runproof_runtime/effectwitness/pge_r70_session.py': {'blob': '2bc9f84ff7625d3face351a6946ad6d5c8ace7e8', 'lf': '08ec12af5106578d9ca9a6b408090f54bf6298bcf4df0a92e6a755d008ea8821'}, 'runtime/runproof_runtime/effectwitness/pge_r71_migration.py': {'blob': 'd6985011f0aff1a0ef96f797ff4bf9f8be0f1224', 'lf': '86da2a4a29c76d731f8e826d5832237e385720e6046b98d942e0242654ee2d7b'}, 'runtime/runproof_runtime/effectwitness/pge_r71_verify.py': {'blob': '8807ba58d054e58968daff977dbdc81ad78e0608', 'lf': 'eab8c3703142f6ed59c74c9cdb45b4108d24db33c6f4199aa7e2c7d987c45181'}, 'runtime/runproof_runtime/effectwitness/pge_r71_session.py': {'blob': '71f9c19c848b0930d81480551574184c2af17998', 'lf': 'b233d43f08e832047d30e96502330f3d1ae902e36842f6bae49b46979df57810'}, 'runtime/runproof_runtime/effectwitness/pge_r72_migration.py': {'blob': 'a8771e7fd994aa7cea41643431ee0e85afbfcf5d', 'lf': '79d036667c030ac3de28da0350990f7d1bc01d1a08500a4f2391829cb808d1ac'}, 'runtime/runproof_runtime/effectwitness/pge_r72_verify.py': {'blob': '373e3756d22e957a532db7a7c3263a72f4d43ed6', 'lf': '10fec4ba8e635f298be04d65e5ceafd778623164e19e69271ffc8d0736f9e5bf'}, 'runtime/runproof_runtime/effectwitness/pge_r72_capability.py': {'blob': '94b61784b27929e704a871cc6159dfac7db51156', 'lf': '25dba0c9e13cadf7825bff0b641eb81e792878901403500aa41ccdd8b9fa5d87'}, 'runtime/runproof_runtime/effectwitness/pge_r72_owner_source.py': {'blob': '033ac2721d609ebe34261d90420472781b20465b', 'lf': 'bc06b8ce05975d9afd4b8f5fd42cfe2f7e8123cc0e81e2e7a4d9ec979340bec2'}, 'runtime/runproof_runtime/effectwitness/pge_r72_session.py': {'blob': 'fe350a90247242031175db1a59e5d352137f10a2', 'lf': 'a4d76afef0d3cbbd9a98d0c1430bfabb4ad3b0379b4796180e5a5b78875f883c'}, 'runtime/runproof_runtime/effectwitness/pge_r72_ports.py': {'blob': 'd226a22118debaccf216e153476a4e374c3fd3ea', 'lf': 'bef3cccd08be3f03d467eaa6e3e037dd642639ebe02930177afd13e982b98ff8'}, 'runtime/runproof_runtime/effectwitness/pge_r72_budget_ledger.py': {'blob': '1f7346cd2ce97c0f1dbd35601633358dda305074', 'lf': 'd9ffe8d543e5a41a4d443359af59888f658685f042e76deac0a1ac780bcd1a7f'}, 'runtime/tests/test_effectwitness_pge_r72.py': {'blob': '4db22ba737e47f26a157a9371e88b5b941ff62ed', 'lf': 'a770c5027c3dd8d6ac04abc89eec54414f3de15741565d17a67333f56a3ba41b'}, 'runtime/__init__.py': {'blob': 'd7a89e7df9ec62d95e768e89ad674e1ce77aca39', 'lf': 'c6e0c83d22491539f41a81edc96d7db4d834ee80fa266e70b6acb2ea36243778'}, 'runtime/tests/__init__.py': {'blob': '13b315b207b2dd91730c3dd702bca475aeb14ff3', 'lf': '9bdd237c2661d4ea0decc14c6cc221785d9d2150336ae50dcef64de5fa73218f'}, 'runtime/runproof_runtime/__init__.py': {'blob': '817d8f1c56cdebddf47d8c879ecba58a1adc1894', 'lf': 'aa545c76886ce9c02d3d7f04f2f27a1cf797a5b1e8e7845f0879328206a12757'}, 'runtime/runproof_runtime/effectwitness/__init__.py': {'blob': '61d072f601e62afad21a5cfd4282d66c8db4228f', 'lf': 'eed7d971a9b3fc80994c5458e21599dcc6df6b0b4734c67fcb6455561613b90b'}, 'ci/runtime-contract-test-matrix.json': {'blob': 'ed827c3dc354c18c9d4b7bc63384805e50e97785', 'lf': '6cebea668a48894277fc65dece2e27c4349610bd9a92c080947ef62c6fcc7a4b'}}
PROSPECTIVE = ('runtime/runproof_runtime/effectwitness.py', 'runtime/runproof_runtime/effectwitness/config_experiment_adapter.py', 'runtime/runproof_runtime/effectwitness/config_experiment_contracts.py', 'runtime/runproof_runtime/effectwitness/config_experiment_verify.py', 'runtime/runproof_runtime/effectwitness/config_live_contracts.py', 'runtime/runproof_runtime/effectwitness/config_live_runtime.py', 'runtime/runproof_runtime/effectwitness/config_live_verify.py', 'runtime/runproof_runtime/effectwitness/contracts.py', 'runtime/runproof_runtime/effectwitness/effect_oracle.py', 'runtime/runproof_runtime/effectwitness/orders.py', 'runtime/runproof_runtime/effectwitness/pge_r68_budget.py', 'runtime/runproof_runtime/effectwitness/pge_r68_config_port.py', 'runtime/runproof_runtime/effectwitness/pge_r68_context.py', 'runtime/runproof_runtime/effectwitness/pge_r68_contracts.py', 'runtime/runproof_runtime/effectwitness/pge_r68_driver.py', 'runtime/runproof_runtime/effectwitness/pge_r68_explorer.py', 'runtime/runproof_runtime/effectwitness/pge_r68_order_port.py', 'runtime/runproof_runtime/effectwitness/pge_r68_session.py', 'runtime/runproof_runtime/effectwitness/pge_r68_verify.py', 'runtime/runproof_runtime/effectwitness/pge_r70_capability.py', 'runtime/runproof_runtime/effectwitness/pge_r70_contracts.py', 'runtime/runproof_runtime/effectwitness/pge_r70_owner_source.py', 'runtime/runproof_runtime/effectwitness/pge_r70_ports.py', 'runtime/runproof_runtime/effectwitness/pge_r70_verify.py', 'runtime/runproof_runtime/effectwitness/pge_r71_budget_ledger.py', 'runtime/runproof_runtime/effectwitness/pge_r71_budget_policy.py', 'runtime/runproof_runtime/effectwitness/pge_r71_capability.py', 'runtime/runproof_runtime/effectwitness/pge_r71_contracts.py', 'runtime/runproof_runtime/effectwitness/pge_r71_owner_source.py', 'runtime/runproof_runtime/effectwitness/pge_r71_ports.py', 'runtime/runproof_runtime/effectwitness/pge_r71_verify.py', 'runtime/runproof_runtime/effectwitness/pge_r72_budget_ledger.py', 'runtime/runproof_runtime/effectwitness/pge_r72_budget_policy.py', 'runtime/runproof_runtime/effectwitness/pge_r72_capability.py', 'runtime/runproof_runtime/effectwitness/pge_r72_contracts.py', 'runtime/runproof_runtime/effectwitness/pge_r72_owner_source.py', 'runtime/runproof_runtime/effectwitness/pge_r72_ports.py', 'runtime/runproof_runtime/effectwitness/pge_r72_sdk_contract.py', 'runtime/runproof_runtime/effectwitness/pge_r72_verify.py', 'runtime/runproof_runtime/models.py')
MAX_JSON = 8*1024*1024
MAX_TOTAL = 64*1024*1024
MAX_LOG = 2*1024*1024
RESOURCES = dict(provider=0, sdk=0, key_lookup=0, java=0, docker=0, external_business_http=0, api_cost=0)

class Invalid(ValueError): pass
def need(ok, code):
    if not ok: raise Invalid(code)
def sha(b): return hashlib.sha256(b).hexdigest()
def canonical(v): return json.dumps(v, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def strict(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_JSON, 'JSON_SIZE')
    def pairs(xs):
        d = {}
        for k,v in xs:
            need(k not in d, 'JSON_DUPLICATE'); d[k] = v
        return d
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(Invalid('JSON_NONFINITE')))
def fields(d, keys): need(type(d) is dict and set(d)==set(keys.split()), 'SCHEMA_FIELDS')
def write(p, value):
    b=canonical(value)+b'\n'; need(len(b)<=MAX_JSON, 'JSON_SIZE')
    with p.open('xb') as f: f.write(b); f.flush(); os.fsync(f.fileno())
def nonlink(p):
    for q in (p,*p.parents):
        try: s=q.lstat()
        except FileNotFoundError: continue
        need(not stat.S_ISLNK(s.st_mode) and not getattr(s,'st_file_attributes',0)&1024, 'REPARSE')
def owned(p, base):
    p=Path(p); base=Path(base)
    need(p.is_absolute() and '..' not in p.parts and p.is_relative_to(base), 'OWNER_LEXICAL')
    nonlink(p); need(p.resolve().is_relative_to(base.resolve()), 'OWNER_RESOLVED')
    return p
def task_root():
    if os.environ.get('GITHUB_ACTIONS')=='true':
        run=os.environ.get('GITHUB_RUN_ID',''); att=os.environ.get('GITHUB_RUN_ATTEMPT','')
        need(re.fullmatch('[0-9]+',run) and re.fullmatch('[0-9]+',att), 'CI_RUN')
        need(os.environ.get('GITHUB_WORKSPACE')==str(ROOT), 'CI_WORKSPACE')
        need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()==os.environ.get('GITHUB_SHA'), 'CI_SHA')
        p=ROOT/'ci-results'/f'rpf88-{run}-{att}'
    else:
        p=Path(os.environ.get('RPF88_TASK_ROOT',''))
        need(p.is_absolute() and p.parent==ROOT/'.local/rpf-88-rev-2' and re.fullmatch('[a-f0-9]{32}',p.name), 'LOCAL_OWNER')
    nonlink(p); return p
def discover(raw, names=NAMES):
    t=ast.parse(raw); classes=[n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='BudgetTests']
    need(len(classes)==1, 'CLASS_SET'); cl=classes[0]
    ms=[n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    need(len(ms)==25 and len({n.name for n in ms})==25 and set(n.name for n in ms)==set(NAMES)|set(EXCLUDED), 'METHOD_SET')
    need(tuple(names)==NAMES and len(names)==18, 'SELECTED_SET')
    return dict(class_ast=sha(ast.dump(cl,include_attributes=False).encode()),
                method_ast={n.name:sha(ast.dump(n,include_attributes=False).encode()) for n in ms},
                assertion_counts={n.name:sum(isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and x.func.attr.startswith('assert') for x in ast.walk(n)) for n in ms})
def identity():
    files={}
    for name,pin in PINS.items():
        raw=(ROOT/name).read_bytes(); need(sha(raw.replace(b'\r\n',b'\n'))==pin['lf'], 'SOURCE_DRIFT')
        files[name]=dict(blob=pin['blob'],raw=sha(raw),lf=pin['lf'])
    inv=discover((ROOT/TARGET).read_bytes())
    matrix=strict((ROOT/'ci/runtime-contract-test-matrix.json').read_bytes())
    row=next(x for x in matrix['modules'] if x['path']==TARGET)
    need(row['source_sha256']==files[TARGET]['lf'] and row['default']=='PORTABLE', 'MATRIX_ROUTE')
    rules=row['rules']; routes={x['selector']:x['route'] for x in rules}
    need(len(rules)==25 and routes=={'BudgetTests.'+n:('WINDOWS_NATIVE' if n==EXCLUDED[-1] else 'DEDICATED_RUNNER') for n in NAMES+EXCLUDED},'MATRIX_EXACT_ROUTES')
    return dict(files=files,inventory=inv,selected=IDS,total_methods=25,dedicated=24,windows_native=1,
                harness_lf_sha256=sha(SELF.read_bytes().replace(b'\r\n',b'\n')))

class Journal:
    def __init__(self,p,source):
        self.fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0),0o600)
        self.seq=0; self.prev=None; self.source=source; self.closed=False
        self.emit('INIT',dict(ids=IDS))
    def emit(self,kind,data):
        need(not self.closed and self.seq<256,'JOURNAL_BOUND')
        v=dict(seq=self.seq,previous=self.prev,pid=os.getpid(),time_ns=time.monotonic_ns(),source=self.source,kind=kind,data=data)
        raw=canonical(v)+b'\n';need(len(raw)<=65536,'JOURNAL_FRAME_SIZE')
        view=memoryview(raw)
        while view:
            n=os.write(self.fd,view);need(n>0,'JOURNAL_WRITE');view=view[n:]
        os.fsync(self.fd);self.prev=sha(raw);self.seq+=1
    def close(self): self.closed=True;os.close(self.fd)
def read_journal(raw,source,pid):
    need(0<len(raw)<=MAX_JSON,'JOURNAL_SIZE');prev=None;last=-1;frames=[];active=None;states={};denials=[];terminal=None
    for line in raw.splitlines(keepends=True):
        need(line.endswith(b'\n'),'JOURNAL_TORN');v=strict(line)
        fields(v,'seq previous pid time_ns source kind data')
        need(type(v['seq']) is int and v['seq']==len(frames)<256 and v['previous']==prev,'JOURNAL_CHAIN')
        need(type(v['pid']) is int and v['pid']==pid and v['source']==source,'JOURNAL_IDENTITY')
        need(type(v['time_ns']) is int and v['time_ns']>last and terminal is None,'JOURNAL_TIME')
        kind=v['kind'];d=v['data'];need(type(d) is dict,'JOURNAL_DATA')
        if kind=='INIT':need(not frames and d==dict(ids=IDS),'JOURNAL_INIT')
        else:need(bool(frames),'JOURNAL_MISSING_INIT')
        if kind=='STARTED':
            fields(d,'id');need(d['id'] in IDS and d['id'] not in states and active is None,'JOURNAL_START')
            active=d['id'];states[active]='STARTED'
        elif kind=='STOP':
            fields(d,'id actual');need(d['id']==active and d['actual'] in ('PASS','FAIL','ERROR','SKIP'),'JOURNAL_STOP');states[active]=d['actual'];active=None
        elif kind=='LISTING':
            fields(d,'event directory_id phase caller_kind decision');need(d['decision']=='ALLOW' and d['caller_kind']=='CPYTHON_FILEFINDER' and d['phase']=='MODULE_IMPORT' and d['event']=='os.listdir' and d['directory_id'] in ('REPO','RUNTIME','TESTS','PACKAGE','EFFECTWITNESS'),'LISTING_FALSE_GREEN')
        elif kind=='DENIED':
            fields(d,'reason method');need(d['method'] is None or d['method'] in IDS,'DENIAL_METHOD');denials.append(d)
        elif kind=='TERMINAL':
            fields(d,'status');need(d['status'] in ('PASS','FAIL'),'TERMINAL_STATUS');terminal=d
        elif kind not in ('INIT','LISTING'):raise Invalid('JOURNAL_KIND')
        frames.append(v);prev=sha(line);last=v['time_ns']
    need(terminal==dict(status='PASS') and active is None and states==dict.fromkeys(IDS,'PASS') and not denials,'JOURNAL_NOT_PASS')
    need([f['data']['id'] for f in frames if f['kind']=='STARTED']==IDS,'JOURNAL_METHOD_ORDER')
    return dict(sha256=sha(raw),frames=len(frames),pid=pid,methods=states,first_ns=frames[0]['time_ns'],last_ns=last)

class Guard:
    """Lexical before metadata; no arbitrary native-syscall coverage claim."""
    def __init__(self,owner,journal=None,source_files=None):
        self.owner=Path(owner);self.journal=journal;self.method=None;self.denied=Counter();self.observed=Counter()
        self.raw_stat=os.stat;self.raw_lstat=os.lstat;self.raw_resolve=Path.resolve
        self.allowed={ROOT/n for n in (source_files if source_files is not None else PINS)}|{SELF,ROOT/'ci/runtime-contract-test-matrix.json'}
        self.allowed_strings={str(p) for p in self.allowed}
        self.prospective={ROOT/n for n in PROSPECTIVE}
        self.parents={p for q in self.allowed|self.prospective|{self.owner} for p in q.parents}
        self.runtime=tuple(dict.fromkeys([Path(sys.base_prefix).absolute(),Path(sys.prefix).absolute(),Path(sysconfig.get_path('stdlib')).absolute()]))
        self.checked=set();self.thread=threading.get_ident()
        self.operation='unknown';self.target_class='unknown';self.events=[];self.phase='SETUP';self.listing_events=[]
        self.import_parents={ROOT:'REPO',ROOT/'runtime':'RUNTIME',ROOT/'runtime/tests':'TESTS',ROOT/'runtime/runproof_runtime':'PACKAGE',ROOT/'runtime/runproof_runtime/effectwitness':'EFFECTWITNESS'}
    def deny(self,code):
        self.denied[code]+=1
        if len(self.events)<16:self.events.append(dict(reason=code,operation=self.operation,method=self.method,target_class=self.target_class,status='DENIED_BEFORE_IO'))
        if self.journal and sum(self.denied.values())<=16:self.journal.emit('DENIED',dict(reason=code,method=self.method))
        raise PermissionError(code)
    def lexical(self,raw,write=False,metadata=False,listing=False):
        if isinstance(raw,int):
            self.deny('FD_OPEN_DENIED')
        try:p=Path(os.fsdecode(raw))
        except (TypeError,ValueError):self.deny('PATH_TYPE')
        self.target_class='fresh_owner' if p.is_relative_to(self.owner) else 'approved_source' if p in self.allowed else 'public_source_parent' if p in self.parents else 'unapproved'
        if not p.is_absolute() or '..' in p.parts:self.deny('PATH_LEXICAL')
        # Windows equality is case-insensitive; require canonical casing for known roots.
        if p.is_relative_to(self.owner):
            if str(p)[:len(str(self.owner))]!=str(self.owner):self.deny('OWNER_CASE_ALIAS')
        elif write:self.deny('WRITE_OUTSIDE_OWNER')
        elif p in self.allowed:
            if listing:self.deny('SOURCE_LIST_DENIED')
            if str(p) not in self.allowed_strings:self.deny('SOURCE_CASE_ALIAS')
        elif metadata and (p in self.parents or p in self.prospective):pass
        elif any(p.is_relative_to(rt) for rt in self.runtime) and not any(x.lower() in ('site-packages','dist-packages') for x in p.parts):
            if not metadata and not listing and p.suffix.lower() not in ('.py','.pyc','.pyd','.so','.dll','.zip','.exe'):self.deny('RUNTIME_NON_SOURCE')
        else:self.deny('UNAPPROVED_PATH')
        return p
    def check(self,raw,write=False,metadata=False,listing=False):
        self.operation='listing' if listing else 'metadata' if metadata else 'write' if write else 'read'
        p=self.lexical(raw,write,metadata,listing)
        if p is None:return
        if p not in self.checked:
            for q in (p,*p.parents):
                try:s=self.raw_lstat(q)
                except FileNotFoundError:continue
                if stat.S_ISLNK(s.st_mode) or getattr(s,'st_file_attributes',0)&1024:self.deny('REPARSE')
            self.checked.add(p)
        self.observed['write' if write else 'metadata' if metadata else 'read']+=1
    def listing(self,event,target):
        p=Path(os.fsdecode(target));caller='OTHER';frame=sys._getframe(1);fill=False;find=False
        import importlib._bootstrap_external as ext
        import importlib._bootstrap as boot
        for _ in range(20):
            if frame is None:break
            fill |= frame.f_code is ext.FileFinder._fill_cache.__code__
            find |= frame.f_code is boot._find_spec.__code__
            frame=frame.f_back
        if fill and find:caller='CPYTHON_FILEFINDER'
        directory=self.import_parents.get(p,'OTHER')
        allow=(event=='os.listdir' and self.phase=='MODULE_IMPORT' and caller=='CPYTHON_FILEFINDER' and directory!='OTHER' and str(p)==str(next(x for x in self.import_parents if x==p)) and '..' not in p.parts)
        row=dict(event=event,directory_id=directory,phase=self.phase,caller_kind=caller,decision='ALLOW' if allow else 'DENY')
        need(len(self.listing_events)<128,'LISTING_EVENT_BOUND');self.listing_events.append(row)
        if self.journal:self.journal.emit('LISTING',row)
        if allow:
            self.check(p,metadata=True);return
        self.operation=event;self.target_class='public_source_parent' if directory!='OTHER' else 'unapproved';self.deny('IMPORT_LISTING_DENIED')
    def audit(self,event,args):
        if event=='open':
            p,mode,flags=args;writing=bool(isinstance(mode,str) and any(x in mode for x in 'wax+') or isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            self.check(p,writing)
        elif event in ('os.listdir','os.scandir'):
            p=Path(os.fsdecode(args[0]))
            if p.is_relative_to(self.owner) or (not p.is_relative_to(ROOT) and any(p.is_relative_to(rt) for rt in self.runtime)):self.check(p,listing=True)
            else:self.listing(event,args[0])
        elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod','os.utime','os.truncate'):self.check(args[0],True)
        elif event in ('os.rename','os.link','os.symlink'):self.deny('LINK_RENAME_DENIED')
        elif event.startswith(('socket.','subprocess.','ctypes.','os.exec','os.spawn','os.posix_spawn')) or event in ('os.system','os.fork','os.forkpty'):self.deny('NETWORK_PROCESS_NATIVE_DENIED')
        elif event=='import' and str(args[0]).split('.')[0] in ('pydantic_ai','openai','httpx','anthropic'):self.deny('SDK_IMPORT_DENIED')
        elif event=='sqlite3.connect':self.sqlite_path(args[0], None)
    def sqlite_path(self,database,uri):
        if not isinstance(database,(str,Path)):self.deny('SQLITE_TYPE')
        value=str(database)
        if value.startswith('file:'):
            u=urlsplit(value)
            if uri is False or u.netloc or u.fragment or parse_qsl(u.query,keep_blank_values=True)!=[('mode','ro')]:self.deny('SQLITE_URI')
            path=unquote(u.path)
            if os.name=='nt' and re.match('/[A-Za-z]:/',path):path=path[1:]
            p=Path(path)
            if '%' in path:self.deny('SQLITE_URI_ENCODING')
        else:
            if uri is True:self.deny('SQLITE_URI_FLAG')
            p=Path(value)
        self.check(p,write=True)
        if p.name!='orders.sqlite3' or not p.is_absolute() or p.parent.name!='business' or not p.is_relative_to(self.owner/'work/rpf72'):self.deny('SQLITE_DATABASE')
        return p
    def install(self):
        g=self
        def wrap_stat(p,*a,**kw):
            if kw.get('dir_fd') is not None:g.deny('DIR_FD')
            g.check(p,metadata=True);return g.raw_stat(p,*a,**kw)
        def wrap_lstat(p,*a,**kw):
            if kw.get('dir_fd') is not None:g.deny('DIR_FD')
            g.check(p,metadata=True);return g.raw_lstat(p,*a,**kw)
        def resolve(p,*a,**kw):g.check(p,metadata=True);return g.raw_resolve(p,*a,**kw)
        os.stat=wrap_stat;os.lstat=wrap_lstat;Path.resolve=resolve
        env_type=type(os.environ);original=env_type.__getitem__
        def env_get(e,key):
            if re.search('KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|DEEPSEEK',str(key),re.I):g.deny('SECRET_LOOKUP_DENIED')
            return original(e,key)
        env_type.__getitem__=env_get
        sys.addaudithook(self.audit)
    def projection(self):return dict(denied=dict(self.denied),denial_events=self.events,observed=dict(self.observed),metadata_intercepts=['os.stat','os.lstat','Path.resolve'],native_boundary='SQLITE_CONNECT_TARGET_ADMISSION',arbitrary_native_syscalls='UNAVAILABLE_NOT_KERNEL_SANDBOX')

def manifest(work):
    rows=[];total=0
    for folder,dirs,files in os.walk(work,followlinks=False):
        need(len(rows)+len(dirs)+len(files)<=512,'MANIFEST_COUNT')
        for n in dirs:nonlink(Path(folder)/n)
        for n in sorted(files):
            p=Path(folder)/n;nonlink(p);s=p.stat();need(stat.S_ISREG(s.st_mode) and s.st_size<=MAX_JSON,'MANIFEST_SIZE');b=p.read_bytes();total+=len(b);need(total<=MAX_TOTAL,'TOTAL_BYTES');rows.append(dict(path=p.relative_to(work).as_posix(),bytes=len(b),sha256=sha(b)))
    return sorted(rows,key=lambda r:r['path'])
def adapter_property(work):
    def root(obj):
        need(type(obj.run_id) is str and re.fullmatch('rpf72-[a-f0-9]{16}',obj.run_id), 'OWNER_RUN')
        return owned(work/'rpf72'/obj.run_id,work)
    return property(root)

class SQLiteAdmission:
    """Target validation only. Original callable, SQL and results unchanged."""
    def __init__(self,guard,work,original):self.guard=guard;self.work=work;self.original=original;self.calls=[]
    def connect(self,database,*args,**kw):
        need(not args and set(kw)<= {'uri','timeout'},'SQLITE_ARGUMENTS')
        if 'uri' in kw:need(type(kw['uri']) is bool,'SQLITE_URI_TYPE')
        p=self.guard.sqlite_path(database,kw.get('uri',False));begin=time.monotonic_ns()
        db=self.original(database,*args,**kw)
        self.calls.append(dict(method=self.guard.method,target=p.relative_to(self.work).as_posix(),readonly=kw.get('uri',False),original_forwarded=True,start_ns=begin,end_ns=time.monotonic_ns()))
        return db

class NativeResult(unittest.TextTestResult):
    def __init__(self,*a,guard,**kw):super().__init__(*a,**kw);self.guard=guard;self.states={}
    def startTest(self,t):super().startTest(t);self.guard.method=t.id();self.states[t.id()]='STARTED';self.guard.journal.emit('STARTED',dict(id=t.id()))
    def addSuccess(self,t):super().addSuccess(t);self.states[t.id()]='PASS'
    def addFailure(self,t,e):super().addFailure(t,e);self.states[t.id()]='FAIL'
    def addError(self,t,e):super().addError(t,e);self.states[t.id()]='ERROR'
    def addSkip(self,t,r):super().addSkip(t,r);self.states[t.id()]='SKIP'
    def addUnexpectedSuccess(self,t):super().addUnexpectedSuccess(t);self.states[t.id()]='FAIL'
    def addExpectedFailure(self,t,e):super().addExpectedFailure(t,e);self.states[t.id()]='FAIL'
    def addSubTest(self,t,sub,e):
        super().addSubTest(t,sub,e)
        if e:self.states[t.id()]='FAIL'
    def stopTest(self,t):self.guard.journal.emit('STOP',dict(id=t.id(),actual=self.states[t.id()]));self.guard.method=None;super().stopTest(t)

def native(folder):
    started=time.monotonic_ns();source=identity();cache=folder/'pycache';cache.mkdir();sys.pycache_prefix=str(cache);need(sys.dont_write_bytecode,'BYTECODE_WRITES')
    work=folder/'work';work.mkdir();journal=Journal(folder/'journal.jsonl',source['harness_lf_sha256']);g=Guard(folder,journal);g.install()
    result=None;error=None;restored=False;sqlite_calls=[];sqlite_restored=False;alias=False
    try:
        sys.path.insert(0,str(ROOT));g.phase='MODULE_IMPORT'
        try:module=importlib.import_module(MODULE)
        finally:g.phase='METHODS'
        s=module.s;before=s.OwnerScope.__dict__['root'];need(s.ROOT==ROOT and s.native.ROOT==ROOT,'ORIGINAL_ROOT')
        orders=importlib.import_module('runtime.runproof_runtime.effectwitness.orders');order_port=importlib.import_module('runtime.runproof_runtime.effectwitness.pge_r68_order_port')
        alias=orders.sqlite3 is sqlite3 and order_port.sqlite3 is sqlite3;need(alias,'SQLITE_MODULE_ALIAS')
        original_connect=sqlite3.connect;sql=SQLiteAdmission(g,work,original_connect);sqlite_calls=sql.calls
        try:
            with patch.object(s.OwnerScope,'root',adapter_property(work)),patch.object(sqlite3,'connect',sql.connect):
                suite=unittest.TestSuite(module.BudgetTests(n) for n in NAMES);need([x.id() for x in suite]==IDS,'NATIVE_IDS')
                result=unittest.TextTestRunner(verbosity=2,resultclass=lambda *a,**kw:NativeResult(*a,guard=g,**kw)).run(suite)
        finally:
            restored=s.OwnerScope.__dict__['root'] is before;sqlite_restored=sqlite3.connect is original_connect
    except Exception as exc:error=type(exc).__name__
    rows=manifest(work);unchanged=identity()==source
    report=dict(schema='rpf88-native-v1',status='FAIL',ids=IDS,states=result.states if result else {},tests_run=result.testsRun if result else 0,
        source=source,pid=os.getpid(),start_ns=started,end_ns=time.monotonic_ns(),guard=g.projection(),sqlite_calls=sqlite_calls,
        sqlite_module_alias=alias,sqlite_wrapper_restored=sqlite_restored,owner_descriptor_restored=restored,
        original_source_unchanged=unchanged,original_test_assertions_unchanged=True,test_only_owner_scope_substitution=True,physical_workspace_fresh=True,
        source_level='SYNTHETIC_OFFLINE_TEST',logical_owner='rpf-72',workspace_contract_bytes_historically_identical=False,
        physical_owner=work.relative_to(ROOT).as_posix(),manifest=rows,cache_empty=not list(cache.iterdir()),error=error,resources=RESOURCES)
    ok=report['states']==dict.fromkeys(IDS,'PASS') and report['tests_run']==18 and not g.denied and restored and sqlite_restored and unchanged and not error and report['cache_empty']
    report['status']='PASS' if ok else 'FAIL';write(folder/'child-result.json',report);journal.emit('TERMINAL',dict(status=report['status']));journal.close()
    return 0 if ok else 1

def validate_native(report,receipt,source,work,journal):
    fields(report,'schema status ids states tests_run source pid start_ns end_ns guard sqlite_calls sqlite_module_alias sqlite_wrapper_restored owner_descriptor_restored original_source_unchanged original_test_assertions_unchanged test_only_owner_scope_substitution physical_workspace_fresh source_level logical_owner workspace_contract_bytes_historically_identical physical_owner manifest cache_empty error resources')
    need(report['schema']=='rpf88-native-v1' and report['status']=='PASS' and report['ids']==IDS and report['states']==dict.fromkeys(IDS,'PASS') and type(report['tests_run']) is int and report['tests_run']==18,'NATIVE_METHODS')
    need(report['source']==source and report['resources']==RESOURCES and all(type(x) is int for x in report['resources'].values()),'NATIVE_SOURCE_RESOURCE')
    for k in ('sqlite_module_alias','sqlite_wrapper_restored','owner_descriptor_restored','original_source_unchanged','original_test_assertions_unchanged','test_only_owner_scope_substitution','physical_workspace_fresh','cache_empty'):need(report[k] is True,'NATIVE_INVARIANT')
    need(report['workspace_contract_bytes_historically_identical'] is False and report['logical_owner']=='rpf-72' and report['source_level']=='SYNTHETIC_OFFLINE_TEST' and report['error'] is None,'NATIVE_CLAIM')
    need(report['physical_owner']==work.relative_to(ROOT).as_posix(),'NATIVE_OWNER')
    validate_receipt(receipt,'native')
    need(type(report['pid']) is int and report['pid']>0 and report['pid']==receipt['pid'],'NATIVE_PID')
    need(receipt['exit']==0 and type(receipt['exit']) is int and receipt['timeout'] is False and receipt['truncated'] is False and receipt['child_exited'] is True and receipt['drain_joined'] is True,'NATIVE_EXIT')
    need(receipt['start_ns']<=report['start_ns']<report['end_ns']<=receipt['end_ns'],'NATIVE_TIME')
    fields(report['guard'],'denied denial_events observed metadata_intercepts native_boundary arbitrary_native_syscalls')
    need(not report['guard']['denied'] and report['guard']['denial_events']==[] and report['guard']['native_boundary']=='SQLITE_CONNECT_TARGET_ADMISSION','NATIVE_DENIAL')
    need(report['guard']['metadata_intercepts']==['os.stat','os.lstat','Path.resolve'] and report['guard']['arbitrary_native_syscalls']=='UNAVAILABLE_NOT_KERNEL_SANDBOX','GUARD_COVERAGE')
    need(type(report['guard']['observed']) is dict and all(k in ('read','write','metadata') and type(v) is int and v>=0 for k,v in report['guard']['observed'].items()),'GUARD_OBSERVED')
    need(report['manifest']==manifest(work) and report['manifest'],'PHYSICAL_MANIFEST')
    j=read_journal(journal,source['harness_lf_sha256'],report['pid'])
    need(report['start_ns']<=j['first_ns']<j['last_ns']<=receipt['end_ns'],'JOURNAL_RECEIPT_TIME')
    calls=report['sqlite_calls'];need(type(calls) is list and 0<len(calls)<=64,'SQLITE_CALLS')
    sqlids=IDS[15:17];seen=set()
    for row in calls:
        fields(row,'method target readonly original_forwarded start_ns end_ns')
        need(row['method'] in sqlids and type(row['readonly']) is bool and row['original_forwarded'] is True,'SQLITE_CALL_ID')
        target=Path(row['target']);need(not target.is_absolute() and '..' not in target.parts and target.name=='orders.sqlite3','SQLITE_TARGET')
        need(re.fullmatch(r'rpf72/rpf72-[a-f0-9]{16}/runs/[^/]+/business/orders.sqlite3',row['target']),'SQLITE_SCOPE')
        owned(work/target,work);need(report['start_ns']<=row['start_ns']<=row['end_ns']<=report['end_ns'],'SQLITE_TIME');seen.add((row['method'],row['readonly']))
    need(seen=={(i,b) for i in sqlids for b in (False,True)},'SQLITE_READ_WRITE_REQUIRED')
    # Independent real read-only SQL observation; never repeat original tests or writes.
    databases=[]
    for row in report['manifest']:
        if not row['path'].endswith('/orders.sqlite3'):continue
        p=owned(work/row['path'],work);uri=p.as_uri()+'?mode=ro'
        with closing(sqlite3.connect(uri,uri=True)) as db:
            db.execute('PRAGMA query_only=ON');refunds=db.execute('SELECT amount_minor,status FROM refunds').fetchall();orders=db.execute('SELECT refunded_minor,status FROM orders').fetchall()
        need(refunds==[(2500,'COMMITTED')] and orders==[(2500,'REFUNDED')],'SQLITE_AUTHORITY_FACTS')
        databases.append(dict(path=row['path'],sha256=row['sha256'],refund_count=1,amount_minor=2500,status='REFUNDED'))
    need(len(databases)==2,'SQLITE_DATABASE_COUNT')
    return dict(status='PASS',journal=j,databases=databases,manifest_sha256=sha(canonical(report['manifest'])))

def validate_receipt(r,mode):
    fields(r,'mode pid exit timeout truncated child_exited drain_joined start_ns end_ns stdout_sha256 report_sha256')
    need(r['mode']==mode and type(r['pid']) is int and r['pid']>0 and type(r['exit']) is int,'RECEIPT_TYPES')
    need(all(type(r[k]) is bool for k in ('timeout','truncated','child_exited','drain_joined')),'RECEIPT_BOOL')
    need(type(r['start_ns']) is int and type(r['end_ns']) is int and 0<r['start_ns']<r['end_ns'] and r['end_ns']-r['start_ns']<=(435 if mode=='native' else 75)*10**9,'RECEIPT_TIME')
    need(all(type(r[k]) is str and re.fullmatch('[a-f0-9]{64}',r[k]) for k in ('stdout_sha256','report_sha256')),'RECEIPT_HASH')

def verify(folder,input_root):
    started=time.monotonic_ns();r=strict((input_root/'native/child-result.json').read_bytes());receipt=strict((input_root/'native/launch-receipt.json').read_bytes());source=identity()
    need(os.getpid()!=r['pid'],'INDEPENDENT_PID');need(receipt['report_sha256']==sha((input_root/'native/child-result.json').read_bytes()) and receipt['stdout_sha256']==sha((input_root/'native/output.log').read_bytes()),'NATIVE_RECEIPT_HASH')
    v=validate_native(r,receipt,source,input_root/'native/work',(input_root/'native/journal.jsonl').read_bytes());need(not list((input_root/'native/pycache').iterdir()),'CACHE_NOT_EMPTY')
    v.update(schema='rpf88-independent-v1',pid=os.getpid(),native_pid=r['pid'],start_ns=started,end_ns=time.monotonic_ns(),source=source,native_report_sha256=receipt['report_sha256'],resources=RESOURCES,original_tests_rerun=False)
    write(folder/'verification.json',v);return 0

def environment(folder):
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','LANG','LC_ALL') if k in os.environ}
    env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',HOME=str(folder),USERPROFILE=str(folder),TEMP=str(folder),TMP=str(folder),TMPDIR=str(folder),RPF88_TASK_ROOT=str(task_root()))
    if os.environ.get('GITHUB_ACTIONS')=='true':env.update({k:os.environ[k] for k in ('GITHUB_ACTIONS','GITHUB_WORKSPACE','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_SHA')})
    return env
def launch(mode,folder,deadline,input_root=None):
    folder=owned(folder,task_root());folder.mkdir(parents=True,exist_ok=False)
    timeout=min(420 if mode=='native' else 60,deadline-time.monotonic());need(timeout>0,'DEADLINE')
    args=[sys.executable,'-B',str(SELF),'--mode',mode,'--output',str(folder)]
    if input_root:args+=['--input-root',str(input_root)]
    start=time.monotonic_ns();p=subprocess.Popen(args,cwd=ROOT,env=environment(folder),stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    data=bytearray();truncated=[False]
    def drain():
        while True:
            b=p.stdout.read(65536)
            if not b:break
            if len(data)+len(b)>MAX_LOG:truncated[0]=True;p.kill()
            if len(data)<MAX_LOG:data.extend(b[:MAX_LOG-len(data)])
    t=threading.Thread(target=drain,daemon=True);t.start();timed=False
    try:p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:timed=True;p.kill();p.wait(timeout=10)
    t.join(timeout=5);end=time.monotonic_ns()
    with (folder/'output.log').open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    report=folder/('child-result.json' if mode=='native' else 'verification.json')
    receipt=dict(mode=mode,pid=p.pid,exit=p.returncode,timeout=timed,truncated=truncated[0],child_exited=p.poll() is not None,drain_joined=not t.is_alive(),start_ns=start,end_ns=end,stdout_sha256=sha(bytes(data)),report_sha256=sha(report.read_bytes()) if report.is_file() else None)
    write(folder/'launch-receipt.json',receipt);return receipt
def public_projection(result):
    return dict(schema='rpf88-public-v1',status=result['status'],source_level='SYNTHETIC_OFFLINE_TEST',ids=IDS,
        results=[dict(id=i,actual=result.get('states',{}).get(i,'NOT_RUN')) for i in IDS],
        eligible_for_future_reconciliation=result['status']=='PASS',formal_coverage_promoted=False,formal_unavailable_remaining=534,
        original_source_unchanged=result.get('source_unchanged',False),test_only_owner_scope_substitution=True,
        physical_workspace_fresh=True,original_test_assertions_unchanged=True,logical_contract_historically_identical=False,
        guard_denied_count=result.get('guard_denied_count'),native_report_sha256=result.get('native_report_sha256'),verification_sha256=result.get('verification_sha256'),
        resources=RESOURCES,no_real_provider_claim=True,release_eligible=False,release_executed=False,deployment_authorized=False)
def run(output):
    root=task_root();need(output==root,'OUTPUT_OWNER');root.mkdir(parents=True,exist_ok=True)
    claim=root/'cohort-claim.json';write(claim,dict(pid=os.getpid(),monotonic_ns=time.monotonic_ns(),formal_cohort_limit=1))
    deadline=time.monotonic()+600;source=identity();status='FAIL';error=None;nr=None;vr=None;report={}
    try:
        nr=launch('native',root/'native',deadline);need(nr['exit']==0 and not nr['timeout'] and not nr['truncated'],'NATIVE_NOT_PASS')
        report=strict((root/'native/child-result.json').read_bytes());vr=launch('verify',root/'verify',deadline,root)
        validate_receipt(vr,'verify');need(vr['exit']==0 and not vr['timeout'] and not vr['truncated'] and vr['child_exited'] and vr['drain_joined'],'VERIFY_NOT_PASS')
        verification=strict((root/'verify/verification.json').read_bytes());need(verification['native_pid']==nr['pid'] and verification['pid']==vr['pid']!=nr['pid'] and verification['status']=='PASS','INDEPENDENT_RECEIPT')
        need(nr['end_ns']<=verification['start_ns']<verification['end_ns']<=vr['end_ns'],'INDEPENDENT_TIME');status='PASS'
    except (Invalid,OSError,ValueError,KeyError,TypeError) as exc:error=str(exc) if isinstance(exc,Invalid) else type(exc).__name__
    if not report and (root/'native/child-result.json').is_file():report=strict((root/'native/child-result.json').read_bytes())
    result=dict(schema='rpf88-result-v1',status=status,error=error,source=source,native_receipt=nr,verify_receipt=vr,states=report.get('states',{}),source_unchanged=report.get('original_source_unchanged',False),guard_denied_count=sum(report.get('guard',{}).get('denied',{}).values()) if report else None,
        native_report_sha256=nr.get('report_sha256') if nr else None,verification_sha256=vr.get('report_sha256') if vr else None,resources=RESOURCES)
    write(root/'result.json',result);write(root/'public-result.json',public_projection(result))
    print('RPF88_'+status+'; original_methods_pass='+str(sum(v=='PASS' for v in result['states'].values()))+'; formal_unavailable_remaining=534; NO_RELEASE/NO_DEPLOY')
    return 0 if status=='PASS' else 1
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['run','native','verify'],default='run');ap.add_argument('--output',required=True);ap.add_argument('--input-root');a=ap.parse_args();root=task_root();p=owned(a.output,root)
    if a.mode=='run':return run(p)
    need(p==root/a.mode,'CHILD_EXACT_OWNER')
    if a.mode=='native':return native(p)
    need(a.input_root==str(root),'VERIFY_INPUT_OWNER');return verify(p,root)
if __name__=='__main__':
    try:sys.exit(main())
    except (Invalid,OSError,ValueError,KeyError,TypeError):print('RPF88_INVALID_FAIL_CLOSED',file=sys.stderr);sys.exit(2)
