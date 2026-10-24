"""Immutable owner and observed source identity; no historical owner alias."""
import ast
import os
import re
from dataclasses import dataclass
from pathlib import Path
from . import pge_r70_contracts as c
from . import pge_r68_context as native

ROOT = Path(__file__).resolve().parents[3]
NEW = tuple('runtime/runproof_runtime/effectwitness/pge_r70_' + x + '.py' for x in
            ('contracts', 'owner_source', 'capability', 'ports', 'session', 'verify', 'migration')) + (
                'runtime/tests/test_effectwitness_pge_r70.py', 'spikes/rpf-70/probe.py')
GUARDS = tuple('runtime/runproof_runtime/effectwitness/' + x for x in
               ('pge_r66_sdk_child_v5.py', 'pge_r67_order_child.py', 'pge_r68_sdk_child.py'))

def source_map():
    pending = list(native.sources()) + list(NEW) + list(GUARDS)
    out = {}
    while pending:
        name = pending.pop()
        if name in out:
            continue
        raw = (ROOT / name).read_bytes()
        out[name] = dict(raw=c.sha(raw), lf=c.sha(raw.replace(b'\r\n', b'\n')),
                         origin='RPF70_CURRENT' if name in NEW else 'NATIVE_READ_ONLY')
        if not name.endswith('.py'):
            continue
        for node in ast.walk(ast.parse(raw)):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.level:
                parent = Path(name).parent
                for _ in range(node.level - 1):
                    parent = parent.parent
                modules = [node.module] if node.module else [a.name for a in node.names]
            elif node.module and node.module.startswith('runtime.'):
                parent, modules = Path('.'), [node.module]
            else:
                continue
            for module in modules:
                path = (parent / (module.replace('.', '/') + '.py')).as_posix()
                if (ROOT / path).is_file():
                    pending.append(path)
    return dict(sorted(out.items()))

def identity():
    sm = source_map()
    return dict(schema=c.VERSION, base=c.BASE, branch=c.BRANCH, source_map=sm,
                raw_digest=c.digest({k: v['raw'] for k, v in sm.items()}),
                lf_digest=c.digest({k: v['lf'] for k, v in sm.items()}),
                native_lf_digest=c.digest({k: v['lf'] for k, v in native.sources().items()}),
                sdk_pin=native.pinned_sdk_fields(), jar_sha256=native.SOURCE_JAR_SHA256,
                jar_bytes=native.SOURCE_JAR_BYTES, issuer=False)

@dataclass(frozen=True, slots=True)
class OwnerScope:
    run_id: str

    def __post_init__(self):
        c.require(type(self.run_id) is str and re.fullmatch(r'rpf70-[a-f0-9]{16}', self.run_id), 'OWNER_RUN')
        self.path(self.root)

    @property
    def root(self):
        return ROOT / '.local/rpf-70/tests' / self.run_id

    def public(self):
        return dict(schema=c.VERSION, owner=c.OWNER, run_id=self.run_id,
                    workspace=self.root.relative_to(ROOT).as_posix(), reset_generation=0)

    def path(self, value):
        p = Path(value)
        c.require(p.is_absolute() and '..' not in p.parts and p.is_relative_to(self.root), 'OWNER_PATH')
        c.require(not any(x.is_symlink() or x.is_junction() for x in (p, *p.parents)), 'OWNER_LINK')
        c.require(p.resolve().is_relative_to(self.root.resolve()), 'OWNER_RESOLVED_PATH')
        return p

@dataclass(frozen=True, slots=True)
class SourceCapsule:
    frozen: bytes

    @classmethod
    def observe(cls):
        return cls(c.canonical(identity()))

    def public(self):
        return c.strict(self.frozen)

    @property
    def raw_sha256(self):
        return c.sha(self.frozen)

    def check(self):
        c.require(type(self.frozen) is bytes, 'SOURCE_TYPE')
        c.equal(self.public(), identity(), 'SOURCE_DECLARED_OBSERVED')
        c.require(self.frozen == c.canonical(self.public()), 'SOURCE_CANONICAL')

class Context:
    def __init__(self, owner, source, ports):
        c.require(type(owner) is OwnerScope and type(source) is SourceCapsule, 'TYPED_OWNER_SOURCE')
        source.check()
        c.require(len(ports) == len(set(ports)) == 3 and all(type(p) is int and 1024 <= p <= 65535 for p in ports), 'PORT_SCOPE')
        self.owner, self.source, self.root = owner, source, owner.root
        sm = source.public()['source_map']
        value = dict(owner=c.OWNER, abi=c.VERSION, session_id=owner.run_id,
                     workspace=owner.public()['workspace'], source_kind=native.SYNTHETIC,
                     provenance=c.KIND, source_capsule_sha256=source.raw_sha256,
                     sources={k: dict(raw=v['raw'], lf=v['lf']) for k, v in sm.items()},
                     source_digest=source.public()['lf_digest'], ports=list(ports), limits=native.LIMITS,
                     caps={k: list(v) for k, v in native.CAPS.items()}, budget_version=native.BUDGET_VERSION,
                     reachable_tokens=native.REACHABLE_TOKENS, global_tokens=native.GLOBAL_TOKENS,
                     max_slot=native.MAX_SLOT, rounds=[])
        for i in (1, 2):
            row = {}
            for candidate in native.CANDIDATES[i-1]:
                ct = native.contract(owner.run_id, i, candidate, value['source_digest'], ports)
                ct['experiment']['owner'] = c.OWNER
                ct['experiment']['environment_id'] = 'env-' + owner.run_id + '-' + native.DOMAINS[i-1]
                row[candidate] = ct
            value['rounds'].append(row)
        self.frozen = c.canonical(value)

    def public(self):
        return c.strict(self.frozen)

    def scope(self, path):
        c.require(type(self.owner) is OwnerScope and self.root == self.owner.root, 'CONTEXT_OWNER')
        return self.owner.path(path)

    def check(self):
        self.scope(self.root)
        self.source.check()
        p = self.public()
        c.require(p['owner'] == c.OWNER and p['session_id'] == self.owner.run_id and
                  p['workspace'] == self.owner.public()['workspace'] and
                  p['source_capsule_sha256'] == self.source.raw_sha256, 'CONTEXT_IDENTITY')

    def validate(self, ct, *, allow_cold=False):
        self.check()
        c.require(not allow_cold and any(c.canonical(ct) == c.canonical(x) for row in self.public()['rounds'] for x in row.values()), 'FROZEN_CONTRACT')

    def contract(self, index, candidate):
        return self.public()['rounds'][index-1][candidate]

    def folder(self, ct):
        self.validate(ct)
        return self.scope(self.root / 'runs' / ct['experiment']['run_id'])

    def once(self, path, value):
        self.check()
        p = self.scope(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open('xb') as f:
            f.write(c.canonical(value))
            f.flush()
            os.fsync(f.fileno())
