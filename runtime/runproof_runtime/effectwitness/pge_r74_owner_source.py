"""Explicit task ownership and source closure for the RPF-74 sessions."""
import ast
import os
from dataclasses import dataclass
from pathlib import Path
from . import pge_r74_contracts as c
from . import pge_r68_contracts as native

# These references are immutable public source, not historical runtime evidence.
REFERENCES = tuple('runtime/runproof_runtime/effectwitness/' + name + '.py' for name in (
    'pge_r68_contracts', 'pge_r68_context', 'pge_r68_budget', 'pge_r68_driver',
    'pge_r68_config_port', 'pge_r68_order_port', 'pge_r68_sdk_child',
    'pge_r72r3_capability', 'pge_r72r3_budget_policy', 'pge_r72r3_launch_spec',
    'orders', 'contracts', 'effect_oracle', 'config_live_runtime',
    'config_live_contracts', 'config_live_verify', 'config_experiment_verify',
    'pge_r73_contracts', 'pge_r73_launch_contract', 'pge_r73_sdk_harness', 'pge_r73_budget_view',
    'pge_r73_domain_adapters')) + ('spikes/rpf-53/probe.py', 'spikes/rpf-55/probe.py',
        'spikes/rpf-53/rev-6/config-live-evidence.json', 'spikes/rpf-73/history-regression.json')

def source_identity():
    files = {}
    pending = list((*c.SOURCE_NAMES, *REFERENCES))
    while pending:
        name = pending.pop()
        if name in files:
            continue
        path = c.ROOT / name
        raw = path.read_bytes()
        files[name] = {'raw': c.sha(raw), 'lf': c.sha(raw.replace(b'\r\n', b'\n'))}
        if name.endswith('.py') and name.startswith('runtime/'):
            for node in ast.walk(ast.parse(raw)):
                if not isinstance(node, ast.ImportFrom) or not node.level:
                    continue
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                candidates = [node.module] if node.module else [alias.name for alias in node.names]
                for module in candidates:
                    if not module:
                        continue
                    target = base / (module.replace('.', '/') + '.py')
                    if target.is_file() and target.is_relative_to(c.ROOT / 'runtime'):
                        pending.append(target.relative_to(c.ROOT).as_posix())
    return {'owner': c.OWNER, 'abi': c.ABI, 'source_kind': c.SOURCE_KIND, 'files': dict(sorted(files.items()))}

@dataclass(frozen=True, slots=True)
class SourceCapsule:
    frozen: bytes

    @classmethod
    def observe(cls):
        return cls(c.canonical(source_identity()))

    def public(self):
        value = c.strict(self.frozen)
        c.require(c.canonical(value) == self.frozen, 'SOURCE_CANONICAL')
        return value

    @property
    def raw_sha256(self):
        return c.sha(self.frozen)

    def check(self):
        c.require(self.public() == source_identity(), 'SOURCE_DRIFT')

@dataclass(frozen=True, slots=True)
class OwnerScope:
    run_id: str

    def __post_init__(self):
        c.run_id(self.run_id)

    @property
    def root(self):
        return c.WORK / 'sessions' / self.run_id

    def public(self):
        return {'owner': c.OWNER, 'abi': c.ABI, 'run_id': self.run_id,
                'workspace': self.root.relative_to(c.ROOT).as_posix()}

    def path(self, value):
        path = Path(value)
        c.require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(self.root), 'OWNER_PATH')
        c.require(not any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)), 'OWNER_LINK')
        c.require(path.resolve().is_relative_to(self.root.resolve()), 'OWNER_RESOLVED_PATH')
        return path

class Context:
    def __init__(self, owner, source, ports, scenario):
        c.require(type(owner) is OwnerScope and type(source) is SourceCapsule, 'TYPED_OWNER_SOURCE')
        c.require(scenario in c.SCENARIOS and len(ports) == len(set(ports)) == 3 and
                  all(type(p) is int and 1024 <= p <= 65535 for p in ports), 'CONTEXT_PARAMETERS')
        source.check()
        self.owner, self.source, self.root, self.scenario = owner, source, owner.root, scenario
        self._writer_owner, self._writer_depth = None, 0
        source_hash = source.raw_sha256
        value = dict(owner=c.OWNER, abi=c.ABI, source_kind=c.SOURCE_KIND, session_id=owner.run_id,
                     workspace=owner.public()['workspace'], source_capsule_sha256=source_hash,
                     ports=list(ports), scenario=scenario, limits=native.LIMITS,
                     caps={k: list(v) for k, v in native.CAPS.items()}, budget_version=native.BUDGET_VERSION,
                     reachable_tokens=native.REACHABLE_TOKENS, global_tokens=native.GLOBAL_TOKENS,
                     max_slot=native.MAX_SLOT)
        value['rounds'] = []
        for index in (1, 2):
            candidate = native.CANDIDATES[index-1][scenario == 'F']
            ct = native.contract(owner.run_id, index, candidate, source_hash, ports)
            ct['experiment']['owner'] = c.OWNER
            ct['experiment']['environment_id'] = 'env-' + owner.run_id + '-' + native.DOMAINS[index-1]
            value['rounds'].append(ct)
        self.frozen = c.canonical(value)

    def public(self):
        return c.strict(self.frozen)

    def scope(self, path):
        c.require(self.root == self.owner.root, 'CONTEXT_OWNER')
        if Path(path) == self.root / 'wal.lock':
            c.require(self._writer_owner is not None and self._writer_depth > 0, 'GATED_WAL_WRITER')
        return self.owner.path(path)

    def check(self):
        self.scope(self.root)
        self.source.check()
        p = self.public()
        c.require(p['owner'] == c.OWNER and p['source_kind'] == c.SOURCE_KIND and
                  p['session_id'] == self.owner.run_id and p['source_capsule_sha256'] == self.source.raw_sha256,
                  'CONTEXT_IDENTITY')

    def validate(self, ct, *, allow_cold=False):
        self.check()
        c.require(not allow_cold and any(c.canonical(ct) == c.canonical(x) for x in self.public()['rounds']),
                  'FROZEN_CONTRACT')

    def folder(self, ct):
        self.validate(ct)
        return self.scope(self.root / 'runs' / ct['experiment']['run_id'])

    def once(self, path, value):
        self.check()
        p = self.scope(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as stream:
            stream.write(c.canonical(value)); stream.flush(); os.fsync(stream.fileno())
