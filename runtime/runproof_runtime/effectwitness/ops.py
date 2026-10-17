"""Controlled SQLite ops state, independent read-only reader and narrow tools.

Reuses RPF-28 release/revision/operation/effect-count/dependency invariants.
This is CONTROLLED_OPS_LOCAL_SIMULATION, not the RPF-28 Docker environment.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import closing

from ..models import RuntimeFailure
from .contracts import ROOT, canonical, owned_path, require
from .cross_core import validate_snapshot
from .ops_oracle import expected_receipt, initial_state
from .orders import AuthoritySnapshot


class OpsSandbox:
    def __init__(self, contracts, directory=None, *, storage_task="rpf-44"):
        contracts.validate()
        require(contracts.experiment["domain"] == "ops", "OPS_DOMAIN_REQUIRED")
        self.contracts = contracts
        require(storage_task in ("rpf-44", "rpf-45"), "STORAGE_TASK_REJECTED")
        self.storage_task = storage_task
        self.directory = owned_path(directory or ROOT / ".local" / storage_task /
                                    contracts.experiment["run_id"], task=storage_task)
        self.path = self.directory / "ops.sqlite3"
        self.generation = 0
        self.created = False

    def initialize(self):
        require(not self.directory.exists(), "ENVIRONMENT_ALREADY_EXISTS", "ENVIRONMENT")
        self.directory.mkdir(parents=True)
        self.created = True
        x, f = self.contracts.experiment, self.contracts.effect
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                PRAGMA journal_mode=DELETE;
                CREATE TABLE environment(owner TEXT, run_id TEXT, environment_id TEXT,
                    environment_revision TEXT, reset_generation INTEGER);
                CREATE TABLE config(config_id TEXT PRIMARY KEY, release TEXT, revision INTEGER,
                    effect_count INTEGER, operation_id TEXT, dependency TEXT);
                CREATE TABLE receipts(operation_id TEXT PRIMARY KEY, config_id TEXT UNIQUE,
                    release TEXT, revision INTEGER, effect_count INTEGER, status TEXT, receipt_id TEXT UNIQUE);
            """)
            db.execute("INSERT INTO environment VALUES(?,?,?,?,0)", tuple(x[k] for k in
                       ("owner", "run_id", "environment_id", "environment_revision")))
            db.execute("INSERT INTO config VALUES(?,?,0,0,NULL,'READY')", (f["config_id"], "release-v1"))
            db.commit()

    def _check(self, db):
        x = self.contracts.experiment
        require(db.execute("SELECT * FROM environment").fetchall() ==
                [tuple(x[k] for k in ("owner", "run_id", "environment_id", "environment_revision"))
                 + (self.generation,)], "ENVIRONMENT_OWNER_OR_GENERATION", "ENVIRONMENT")

    def apply(self, config_id, operation_id, release):
        f, x = self.contracts.effect, self.contracts.experiment
        require(self.generation == 0, "ENVIRONMENT_RESET_REQUIRES_NEW_EXPERIMENT", "ENVIRONMENT")
        require({"config_id": config_id, "operation_id": operation_id, "release": release} ==
                {k: f[k] for k in ("config_id", "operation_id", "release")}, "APPLY_NOT_ALLOWLISTED", "AGENT")
        require(self.path.is_file(), "ENVIRONMENT_MISSING", "ENVIRONMENT")
        with closing(sqlite3.connect(self.path, timeout=5)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._check(db)
            old = db.execute("SELECT receipt_id FROM receipts WHERE operation_id=?", (operation_id,)).fetchone()
            if old:
                db.commit()
                return {"status": "IDEMPOTENT_REPLAY", "operation_id": operation_id, "receipt_id": old[0]}
            row = db.execute("SELECT * FROM config").fetchone()
            require(row == tuple(initial_state(f).values()), "CONFIG_PRECONDITION_OR_DEPENDENCY", "AGENT")
            receipt = expected_receipt(f, x["environment_id"])
            db.execute("INSERT INTO receipts VALUES(?,?,?,?,?,?,?)", tuple(receipt[k] for k in
                       ("operation_id", "config_id", "release", "revision", "effect_count", "status", "receipt_id")))
            db.execute("UPDATE config SET release=?,revision=1,effect_count=1,operation_id=? WHERE config_id=?",
                       (release, operation_id, config_id))
            db.commit()
        return {"status": "APPLIED", "operation_id": operation_id, "receipt_id": receipt["receipt_id"]}

    def cleanup(self):
        f = self.contracts.effect
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("BEGIN IMMEDIATE")
            self._check(db)
            db.execute("DELETE FROM receipts")
            db.execute("UPDATE config SET release='release-v1',revision=0,effect_count=0,operation_id=NULL,dependency='READY'")
            db.execute("UPDATE environment SET reset_generation=reset_generation+1")
            db.commit()
            require(db.execute("SELECT * FROM config").fetchall() == [tuple(initial_state(f).values())]
                    and db.execute("SELECT count(*) FROM receipts").fetchone()[0] == 0
                    and db.execute("SELECT reset_generation FROM environment").fetchone()[0] == 1,
                    "RESET_READBACK_FAILED", "ENVIRONMENT")
        self.generation = 1
        for suffix in ("", "-journal", "-wal", "-shm"):
            path = owned_path(self.path.with_name(self.path.name + suffix), task=self.storage_task)
            if path.exists():
                path.unlink()
        self.directory.rmdir()
        return {"status": "RESET_AND_REMOVED", "reset_generation": 1, "receipt_count_after_reset": 0}


class OpsAuthorityReader:
    def __init__(self, path, contracts, *, storage_task="rpf-44"):
        self.path = owned_path(path, task=storage_task)
        self.contracts = contracts
        self._seal = secrets.token_bytes(32)
        self.available = True

    def read(self):
        require(self.available and self.path.is_file(), "AUTHORITY_UNAVAILABLE", "ENVIRONMENT")
        try:
            with closing(sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                db.execute("BEGIN")
                environments = [dict(r) for r in db.execute("SELECT * FROM environment")]
                states = [dict(r) for r in db.execute("SELECT * FROM config")]
                require(len(environments) == len(states) == 1, "AUTHORITY_CARDINALITY", "ENVIRONMENT")
                receipts = [dict(r) for r in db.execute("SELECT * FROM receipts ORDER BY operation_id")]
                db.commit()
        except sqlite3.Error as error:
            raise RuntimeFailure("ENVIRONMENT", "AUTHORITY_READ_ERROR") from error
        data = {"reader_id": "rpf44-sqlite-ops-reader", "reader_version": "1",
                "source_id": self.contracts.effect["authority_id"], "environment": environments[0],
                "config": states[0], "receipts": receipts}
        raw = canonical(data)
        return AuthoritySnapshot(raw, hashlib.sha256(raw).hexdigest(), hmac.digest(self._seal, raw, "sha256"))

    def validate(self, snapshot):
        require(isinstance(snapshot, AuthoritySnapshot), "AUTHORITY_SNAPSHOT_MISSING", "ENVIRONMENT")
        require(hashlib.sha256(snapshot.payload).hexdigest() == snapshot.sha256
                and hmac.compare_digest(snapshot._attestation, hmac.digest(self._seal, snapshot.payload, "sha256")),
                "AUTHORITY_HASH_OR_ISSUER_MISMATCH", "ENVIRONMENT")
        from .witness_verify import VerificationRejected
        try:
            return validate_snapshot(snapshot.public(), self.contracts.effect, self.contracts.experiment, "ops")
        except VerificationRejected as error:
            raise RuntimeFailure("ENVIRONMENT", error.code) from error

    def reconcile(self, operation_id):
        data = self.validate(self.read())
        expected = expected_receipt(self.contracts.effect, self.contracts.experiment["environment_id"])
        require(operation_id == self.contracts.effect["operation_id"] and data["receipts"] == [expected],
                "RECONCILE_RECEIPT_MISMATCH", "ENVIRONMENT")
        return data["receipts"][0]


class OpsAdapter:
    def __init__(self, sandbox):
        self.sandbox, self.contracts = sandbox, sandbox.contracts
        self.fault = {"planned": self.contracts.experiment["fault"] != "none",
                      "triggered": False, "observed": False, "reconciled": False}

    def tool_definitions(self):
        f = self.contracts.effect
        return [{"type": "function", "function": {"name": name, "description": "Controlled local config tool",
                 "parameters": {"type": "object", "properties": {k: {"type": "string", "enum": [f[k]]}
                 for k in keys}, "required": list(keys), "additionalProperties": False}}}
                for name, keys in (("inspect_config", ("config_id",)),
                                   ("apply_config", ("config_id", "operation_id", "release")))]

    def invoke(self, name, arguments):
        require(name in self.contracts.execution["tools"], "TOOL_NOT_ALLOWLISTED", "AGENT")
        keys = ("config_id",) if name == "inspect_config" else ("config_id", "operation_id", "release")
        require(type(arguments) is dict and arguments == {k: self.contracts.effect[k] for k in keys},
                "TOOL_ARGUMENTS_REJECTED", "AGENT")
        if name == "inspect_config":
            reader = OpsAuthorityReader(self.sandbox.path, self.contracts, storage_task=self.sandbox.storage_task)
            return reader.validate(reader.read())["config"]
        result = self.sandbox.apply(**arguments)
        if result["status"] == "APPLIED" and self.contracts.experiment["fault"] == "response-lost":
            self.fault.update(triggered=True, observed=True)
            return {"status": "UNKNOWN_OUTCOME", "operation_id": self.contracts.effect["operation_id"],
                    "reason": "CONTROLLED_POST_COMMIT_RESPONSE_LOSS"}
        return result
