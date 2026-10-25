"""Historical launch environment ABI. Raw environment stays in private evidence.

Live observation compares actual audit env with the contemporaneous native helper.
Offline checks use only this frozen snapshot, never current host safe variables.
Controller observations are not independent child signatures or an OS sandbox.
"""
from dataclasses import dataclass
import ntpath
from pathlib import Path
import re
import subprocess
import sys
from . import pge_r72r3_contracts as c
from . import pge_r68_context as n

SCHEMA='rpf72r3-launch-spec-v1'
CHILD='runtime/runproof_runtime/effectwitness/pge_r68_sdk_child.py'
ENV_KEYS=frozenset(('SYSTEMROOT','WINDIR','PATH','HOME','USERPROFILE','TEMP','TMP',
                    'PYTHONDONTWRITEBYTECODE','OTEL_SDK_DISABLED','LOGFIRE_SEND_TO_LOGFIRE'))

# Frozen G0 directory identities, not current-host lookups. No raw PATH values.
TRUSTED_PATH_SHA256=frozenset(('00f8b8cbb9af9e364927848a028a8701a4fb507bbbbe243b2518af80465e9e86', '014aa9d237a0e18e1b69e27ca4096b17d3c486e3742d112c138e8e6426972e60', '225d60148d76b58a2a53ec77c227bfe213d14b9e7dd4aecc126ebc761157607c', '30ad97306e840ecae36cbc6200cb570285372375acd17de2cd618c53b189a4db', '437e794a62a8702e7d37a6259dce154871cc39691889136fb313ac54fa15b804', '44064d11f679cc0b6267765e9a7bb1a4b72d41ffbde39eca66d2bf77d4174328', '49bc09e070e6e523e9c7f5bf6692889cc152dadb1177030a2a337b5c1a9cebc1', '4b0b8707b7ff3b423fb3d4e3d298c4822658eff5075182f91708acfcf225cc49', '4ef46d6cbaf800c51baa2ee04d6d41a6bd9426c18b8ab414acd45153c69a6dd0', '51f32b16736a8a096eb62d91d77715222cac8b0b9e9b0573d6d9d1526c19454c', '57f0d824073cbbe42f4fc521197c78296684f031361fd78e42a9434700d20363', '619a48646d47c89662372eefbae914fd08386308ead63acde0dc5bcdb03b09eb', '726f3091397f5ecbd73759b5d4114b1f21e81eb5ad4442b19b47d881d73f02f3', '780a6590b675021c90192abf679b86722a542bb3ab84bccf484c391c5003d132', '7f9a8f39b04351dde6fe0a9a43c289118e203e452f262c9ac473cc72a7b98eee', '831c97b449e9e781772d3e1939a82f680d9e064962f73ac85aca39f0683abe41', '857f38bb17b98d5fa9b4f41a4bcffe9bd43d2307eabd3f0e322f58997ff83e08', '8bb05e2304727e6becdc954492cd4e9eb6f03697916bcb2f277a551e0ef5b3f3', 'a79e62e75ce3e8f96917afeb3ba210760382550ad622665155693fdb594e8180', 'add36437b4e77e4fd4c12975780fcc475759d88d39945e695f1a46bfc6ddd725', 'b1cdeacf435591ed965e574fa652d8cb6e87523425eb9593f4b3ef64f1a82b72', 'ba801032df8634c03d97bae0c3ce6f6d243312e6eb4e510dfcd9b3e422aafcb1', 'bd4fea5b11684e7e768c5918cf9c5b5162164b655a033d5996ea4808e52d7421', 'be237fc70c9fe65a8765a61858617c24d0d77cd0578601f55fa774b9e7296094', 'c4917286e548de28a2e9adbe973a12831373f29603fe3c97999a5aebf548e332', 'c53a4215accb368fae59e2e70468c7b6108bae9806e8aaa189eed9dc698b11cc', 'c6af5cc308e7f18396e3bf889242137c8c1ad9709032afd0d5db8101efd274e7', 'cc18e488534b701c700d244fd8b825764668528a12be5d445ae7223625ea724c', 'cf4af2a70e98ffe1d5d97b6e8d3707851525db8f44ff2f1f9ba59a22beb24915', 'd2d9b2c24fd30ad0af1b4d1e54b5870af582338c1a11ec527adac976f9264751', 'd48108d0a57808196bd48a9a27bc3e0104f48592cd67426935cc27dcc7d97b9b', 'd6e1816a76c996d66f108e5a10777a93ae95a1428e1cf9bd4f92e09f29358eec', 'dc9ca79eef0c352cf1c13e9c6faac1affaa448c2182999cdc7d91408f54e9ce0', 'ed014bb5bf8c509dec56f446cb47b8f34d50271918242af6b0f53e7b68de96a7', 'f33ffb0681cf1341c4f2f461b047acdb678f85badac87dea5e08a853b88d2268'))
SYSTEM_ROOT_SHA256='c53a4215accb368fae59e2e70468c7b6108bae9806e8aaa189eed9dc698b11cc'

def path_identity(value):
    return c.sha(ntpath.normcase(ntpath.normpath(value)).encode())

def environment(env,folder):
    c.require(type(env) is dict and set(env)==ENV_KEYS,'LAUNCH_ENV_KEYS')
    c.require(all(type(k) is str and type(v) is str and 0<len(v)<=32768 and
                  not any(ch in v for ch in '\r\n\0') for k,v in env.items()),'LAUNCH_ENV_TYPES')
    c.require(not any(re.search(r'(?:Bearer\s+|sk-[A-Za-z0-9]{16,}|api[_-]?key\s*=)',v,re.I)
                      for v in env.values()),'LAUNCH_ENV_SECRET_SYNTAX')
    for key in ('HOME','USERPROFILE','TEMP','TMP'):
        c.require(env[key]==str(folder),'LAUNCH_ENV_TASK_ROOT')
    c.require(env['PYTHONDONTWRITEBYTECODE']=='1' and env['OTEL_SDK_DISABLED']=='true' and
              env['LOGFIRE_SEND_TO_LOGFIRE']=='false','LAUNCH_ENV_FLAGS')
    for key in ('SYSTEMROOT','WINDIR'):
        value=env[key]
        c.require(ntpath.isabs(value) and not value.startswith(('\\\\','//')) and
                  '..' not in value.replace('/','\\').split('\\') and '%' not in value and
                  not any(ch in value for ch in '"|&<>;'),'LAUNCH_SYSTEM_PATH')
    c.require(ntpath.normcase(ntpath.normpath(env['SYSTEMROOT']))==
              ntpath.normcase(ntpath.normpath(env['WINDIR'])),'LAUNCH_SYSTEM_ROOT_PAIR')
    c.require(path_identity(env['SYSTEMROOT'])==SYSTEM_ROOT_SHA256,'LAUNCH_SYSTEM_ROOT_IDENTITY')
    entries=env['PATH'].split(';')
    c.require(all(p and ntpath.isabs(p) and not p.startswith(('\\\\','//')) and
                  '..' not in p.replace('/','\\').split('\\') and '%' not in p and '://' not in p and
                  not any(ch in p for ch in '"|&<>') for p in entries),'LAUNCH_PATH_ABSOLUTE_ONLY')
    c.require(all(path_identity(p) in TRUSTED_PATH_SHA256 for p in entries),'LAUNCH_PATH_TRUSTED_DIRECTORY')
    return dict(env_sha256=c.digest(env),env_keys=sorted(env),
                value_sha256={k:c.sha(v.encode()) for k,v in sorted(env.items())})

def binding(ctx,policy,ct,capsule,folder):
    policy.check(ctx);ctx.validate(ct);cap=capsule.public()
    c.require(cap['policy_sha256']==policy.raw_sha256 and cap['owner']==ctx.owner.public(), 'LAUNCH_OWNER_POLICY')
    c.require(folder==ctx.scope(ctx.root/'runs'/ct['experiment']['run_id']/'sdk'),'LAUNCH_CWD_SCOPE')
    h,_=n.helpers();pin=cap['sdk_pin'];direct=h.resolve_direct_python(pin)
    argv=[str(direct),'-I','-B','-X','utf8',str(n.ROOT/CHILD)]
    c.require(c.sha(Path(direct).read_bytes())==pin['python_executable_sha256'] and
              c.sha((n.ROOT/CHILD).read_bytes())==cap['child_raw_sha256'],'LAUNCH_FIXED_PINS')
    return dict(schema=SCHEMA,owner=ctx.owner.public(),source_kind=c.KIND,
                source_capsule_sha256=ctx.source.raw_sha256,policy_sha256=policy.raw_sha256,
                parent_child_contract_sha256=capsule.raw_sha256,contract_sha256=c.digest(ct),
                domain=ct['experiment']['domain'],round=ct['experiment']['round'],role='TARGET',
                run_id=ct['experiment']['run_id'],cwd=str(folder),cwd_relative=folder.relative_to(ctx.root).as_posix(),
                argv=argv,command=subprocess.list2cmdline(argv),executable_type='NoneType',argv_type='str',
                python_executable_sha256=pin['python_executable_sha256'],child_raw_sha256=cap['child_raw_sha256'],
                sdk_pin_sha256=c.digest(pin),platform='WINDOWS',architecture='x86_64',
                shell=False,issuer=False,observation='CONTROLLER_OBSERVED')

@dataclass(frozen=True,slots=True)
class LaunchSpec:
    frozen:bytes

    @classmethod
    def observe(cls,args,ctx,policy,ct,capsule,folder,expected_env):
        c.require(sys.platform=='win32' and sys.maxsize>2**32,'LAUNCH_PLATFORM')
        base=binding(ctx,policy,ct,capsule,folder)
        c.require(type(args) is tuple and len(args)==4,'LAUNCH_AUDIT_SHAPE')
        c.require(args[0] is None and type(args[1]) is str and args[1]==base['command'],'LAUNCH_AUDIT_COMMAND')
        c.require(type(args[2]) is str and args[2]==str(folder),'LAUNCH_AUDIT_CWD')
        environment(args[3],folder);environment(expected_env,folder)
        c.equal(args[3],expected_env,'LAUNCH_LIVE_ENV_EXACT')
        summary=environment(args[3],folder)
        obj=dict(base,sanitized_env=dict(args[3]),env_sha256=summary['env_sha256'],env_keys=summary['env_keys'],
                 env_value_sha256=summary['value_sha256'],command_sha256=c.sha(args[1].encode()),
                 audit_tuple_types=['NoneType','str','str','dict'],live_env_exact=True)
        return cls(c.canonical(obj))

    def public(self):
        c.require(type(self.frozen) is bytes,'LAUNCH_BYTES')
        value=c.strict(self.frozen)
        c.require(self.frozen==c.canonical(value),'LAUNCH_CANONICAL')
        return value

    @property
    def raw_sha256(self):return c.sha(self.frozen)

    def check(self,ctx,policy,ct,capsule,folder):
        value=self.public();base=binding(ctx,policy,ct,capsule,folder)
        c.require(set(value)==set(base)|{'sanitized_env','env_sha256','env_keys','env_value_sha256',
                                       'command_sha256','audit_tuple_types','live_env_exact'},'LAUNCH_SPEC_FIELDS')
        c.equal({k:value[k] for k in base},base,'LAUNCH_FROZEN_BINDING')
        summary=environment(value['sanitized_env'],folder)
        c.require(value['env_sha256']==summary['env_sha256'] and value['env_keys']==summary['env_keys'],'LAUNCH_ENV_RAW_BINDING')
        c.equal(value['env_value_sha256'],summary['value_sha256'],'LAUNCH_ENV_PER_KEY_BINDING')
        c.require(value['command_sha256']==c.sha(value['command'].encode()) and value['live_env_exact'] is True and
                  value['audit_tuple_types']==['NoneType','str','str','dict'],'LAUNCH_OBSERVATION_FIELDS')
        return dict(status='PASS',env_sha256=value['env_sha256'],launch_spec_sha256=self.raw_sha256,
                    observation='CONTROLLER_OBSERVED',child_attestation='NOT_ESTABLISHED')

    def redacted(self):
        value=self.public()
        return {k:v for k,v in value.items() if k not in ('sanitized_env','argv','command','cwd')}
