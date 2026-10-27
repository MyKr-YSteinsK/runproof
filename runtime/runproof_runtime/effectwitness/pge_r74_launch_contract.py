"""Versioned launch request for one task-owned SDK child."""
from dataclasses import dataclass
import importlib.util
import os
from pathlib import Path
import secrets
import re
import subprocess
from . import pge_r74_contracts as c
from . import pge_r68_contracts as native
from . import pge_r73_contracts as pins
from .pge_r73_launch_contract import live_environment, env_summary
from .pge_r74_owner_source import Context

def fixed_paths():
    # The full Runtime suite explicitly injects its already-approved public SDK
    # reference root. Normal task execution uses this module's own repository.
    reference = Path(os.environ.get('RPF68_FIXED_SDK_PUBLIC_ROOT', str(c.ROOT)))
    c.require(reference.is_absolute() and not any(p.is_symlink() or p.is_junction() for p in (reference,*reference.parents)),
              'SDK_REFERENCE_SCOPE')
    if reference == c.ROOT:
        return pins.fixed_paths()
    source = reference/'runtime/runproof_runtime/effectwitness/pge_r73_contracts.py'
    c.require(source.is_file() and c.sha(source.read_bytes()) == c.sha(Path(pins.__file__).read_bytes()),
              'SDK_REFERENCE_SOURCE')
    spec = importlib.util.spec_from_file_location('rpf74_pinned_reference', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    c.require(module.PIN == pins.PIN, 'SDK_REFERENCE_PIN')
    return module.fixed_paths()

@dataclass(frozen=True, slots=True)
class LaunchRequest:
    frozen: bytes

    def public(self):
        value = c.strict(self.frozen)
        c.require(c.canonical(value) == self.frozen, 'LAUNCH_CANONICAL')
        return value

    @property
    def raw_sha256(self):
        return c.sha(self.frozen)

    @classmethod
    def build(cls, ctx, ct):
        c.require(type(ctx) is Context, 'LAUNCH_CONTEXT')
        ctx.validate(ct)
        fixed = fixed_paths()
        domain = ct['experiment']['domain']
        folder = ctx.scope(ctx.folder(ct) / 'sdk')
        env = live_environment(folder)
        cfg = dict(port=ct['execution']['host_port'], token=secrets.token_hex(32),
                   write_root=str(folder), sdk_readonly_path=fixed['site'],
                   sdk_site_root_binding_sha256=pins.PIN['sdk_site_root_binding_sha256'],
                   python_runtime_mapping_sha256=pins.PIN['python_runtime_mapping_sha256'],
                   instructions=native.INSTRUCTIONS[domain], task_prompt=native.prompt(ct),
                   domain=domain, total_token_limit=sum(native.CAPS[domain]))
        argv = [fixed['python'], '-I', '-B', '-X', 'utf8', fixed['child']]
        value = dict(schema=c.ABI, owner=c.OWNER, source_kind=c.SOURCE_KIND,
                     source_sha256=ctx.source.raw_sha256, run_id=ctx.owner.run_id,
                     domain=domain, scenario=ctx.scenario, cwd=str(folder), argv=argv,
                     windows_command=subprocess.list2cmdline(argv), env=env,
                     env_summary=env_summary(env, folder), cfg=cfg,
                     cfg_sha256=c.digest(cfg), timeout_seconds=900, issuer=False)
        request = cls(c.canonical(value))
        request.check(ctx, ct)
        return request

    def check(self, ctx, ct):
        ctx.validate(ct)
        value = self.public()
        c.require(set(value) == {'schema','owner','source_kind','source_sha256','run_id','domain','scenario',
                  'cwd','argv','windows_command','env','env_summary','cfg','cfg_sha256','timeout_seconds','issuer'},
                  'LAUNCH_FIELDS')
        fixed = fixed_paths()
        domain = ct['experiment']['domain']
        folder = ctx.scope(ctx.folder(ct) / 'sdk')
        c.require(value['schema'] == c.ABI and value['owner'] == c.OWNER and
                  value['source_kind'] == c.SOURCE_KIND and value['source_sha256'] == ctx.source.raw_sha256 and
                  value['run_id'] == ctx.owner.run_id and value['domain'] == domain and
                  value['scenario'] == ctx.scenario and value['cwd'] == str(folder), 'LAUNCH_SCOPE')
        argv = [fixed['python'], '-I', '-B', '-X', 'utf8', fixed['child']]
        c.require(value['argv'] == argv and value['windows_command'] == subprocess.list2cmdline(argv) and
                  value['timeout_seconds'] == 900 and value['issuer'] is False, 'LAUNCH_COMMAND')
        c.require(value['env_summary'] == env_summary(value['env'], folder) and
                  value['env'] == live_environment(folder), 'LAUNCH_ENV')
        cfg = value['cfg']
        c.require(type(cfg) is dict and set(cfg) == {'port','token','write_root','sdk_readonly_path',
                  'sdk_site_root_binding_sha256','python_runtime_mapping_sha256','instructions','task_prompt',
                  'domain','total_token_limit'} and cfg['port'] == ct['execution']['host_port'] and
                  cfg['write_root'] == str(folder) and cfg['sdk_readonly_path'] == fixed['site'] and
                  cfg['sdk_site_root_binding_sha256'] == pins.PIN['sdk_site_root_binding_sha256'] and
                  cfg['python_runtime_mapping_sha256'] == pins.PIN['python_runtime_mapping_sha256'] and
                  type(cfg['port']) is int and 1024 <= cfg['port'] <= 65535 and
                  type(cfg['token']) is str and re.fullmatch('[a-f0-9]{64}', cfg['token']) and
                  cfg['instructions'] == native.INSTRUCTIONS[domain] and cfg['task_prompt'] == native.prompt(ct) and
                  cfg['domain'] == domain and cfg['total_token_limit'] == sum(native.CAPS[domain]) and
                  type(cfg['total_token_limit']) is int and len(c.canonical(cfg)) <= 16384 and
                  value['cfg_sha256'] == c.digest(cfg), 'LAUNCH_CFG')
        return value
